from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from marketatlas.analysis.ast.expressions import (
    ChoiceExpression,
    LiteralExpression,
    ReferenceExpression,
    choice_leaves,
)
from marketatlas.analysis.ast.lexer import SourcePosition
from marketatlas.analysis.ast.models import Analysis, Definition, is_timeframe_definition
from marketatlas.data.types import Timeframe


class DiagnosticSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    """Semantic/compiler finding with an optional source location (backlog 059).

    ``position`` is ``None`` when the error was produced from an AST with no
    source mapping (builder-constructed, deserialized). Lexer/parser errors
    raise their own positioned exceptions (``DslSyntaxError``/``DslParseError``)
    instead of ``Diagnostic``.
    """

    message: str
    severity: DiagnosticSeverity
    node_name: str
    node_type: str
    position: SourcePosition | None = None


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: tuple[Diagnostic, ...] = ()
    warnings: tuple[Diagnostic, ...] = ()

    @staticmethod
    def ok() -> ValidationResult:
        return ValidationResult(is_valid=True)


def _reference_edges(definitions: Sequence[Definition]) -> list[tuple[str, str]]:
    """Reference edges (producer name, consumer name) across all parameters.

    A ``ReferenceExpression`` parameter value names the definition it consumes
    (backlog 061): the dependency graph is the compile-time helper that replaced
    the retired ``Binding`` node. Nested choice leaves are included so template
    choices over references participate in cycle detection.
    """
    edges: list[tuple[str, str]] = []
    for d in definitions:
        for p in d.parameters:
            for leaf in choice_leaves(p.value):
                if isinstance(leaf, ReferenceExpression):
                    edges.append((leaf.name, d.name))
    return edges


def _detect_cycles(definitions: Sequence[Definition]) -> list[list[str]]:
    name_to_idx: dict[str, int] = {}
    for i, d in enumerate(definitions):
        name_to_idx[d.name] = i

    adjacency: list[list[int]] = [[] for _ in range(len(definitions))]
    for source, target in _reference_edges(definitions):
        if source in name_to_idx and target in name_to_idx:
            src_idx = name_to_idx[source]
            t_idx = name_to_idx[target]
            adjacency[src_idx].append(t_idx)

    white, gray, black = 0, 1, 2
    color = [white] * len(definitions)
    parent = [-1] * len(definitions)
    cycles: list[list[str]] = []

    def dfs(u: int) -> None:
        color[u] = gray
        for v in adjacency[u]:
            if color[v] == gray:
                cycle = [definitions[v].name]
                cur = u
                while cur != v:
                    cycle.append(definitions[cur].name)
                    cur = parent[cur]
                cycle.append(definitions[v].name)
                cycles.append(cycle[::-1])
            elif color[v] == white:
                parent[v] = u
                dfs(v)
        color[u] = black

    for i in range(len(definitions)):
        if color[i] == white:
            dfs(i)

    return cycles


def _provider_category(
    definition: Definition, categories: dict[str, str]
) -> str | None:
    return categories.get(definition.provider)


def validate(analysis: Analysis) -> ValidationResult:
    errors: list[Diagnostic] = []
    warnings: list[Diagnostic] = []

    provider_names = {p.name for p in analysis.providers}
    categories = {p.name: p.category for p in analysis.providers}
    def_by_name = {d.name: d for d in analysis.definitions}

    seen_names: set[str] = set()
    ref_counts: dict[str, int] = {}

    for d in analysis.definitions:
        if d.name in seen_names:
            errors.append(
                Diagnostic(
                    message=f"Duplicate definition name: {d.name}",
                    severity=DiagnosticSeverity.ERROR,
                    node_name=d.name,
                    node_type="definition",
                )
            )
        seen_names.add(d.name)
        ref_counts.setdefault(d.name, 0)

        if not d.provider:
            errors.append(
                Diagnostic(
                    message="Definition has empty provider",
                    severity=DiagnosticSeverity.ERROR,
                    node_name=d.name,
                    node_type="definition",
                )
            )
        elif d.provider not in provider_names:
            valid_str = ", ".join(sorted(provider_names)) if provider_names else "(none)"
            errors.append(
                Diagnostic(
                    message=f"Unknown provider: '{d.provider}'. "
                    f"Available providers: {valid_str}",
                    severity=DiagnosticSeverity.ERROR,
                    node_name=d.name,
                    node_type="definition",
                )
            )

        consumer_category = _provider_category(d, categories)
        for p in d.parameters:
            for leaf in choice_leaves(p.value):
                if not isinstance(leaf, ReferenceExpression):
                    continue
                target = def_by_name.get(leaf.name)
                if target is None:
                    errors.append(
                        Diagnostic(
                            message=f"Unknown reference: definition '{d.name}' "
                            f"references '{leaf.name}', which is not defined",
                            severity=DiagnosticSeverity.ERROR,
                            node_name=d.name,
                            node_type="definition",
                        )
                    )
                    continue
                ref_counts[leaf.name] = ref_counts.get(leaf.name, 0) + 1

                target_category = _provider_category(target, categories)
                if is_timeframe_definition(target) or target_category == "timeframe":
                    if consumer_category not in (None, "analyzer"):
                        errors.append(
                            Diagnostic(
                                message=(
                                    f"Reference to TimeFrame definition '{leaf.name}' "
                                    f"from '{d.name}' is only valid on analyzer "
                                    f"definitions, not '{consumer_category}'"
                                ),
                                severity=DiagnosticSeverity.ERROR,
                                node_name=d.name,
                                node_type="definition",
                            )
                        )
                    continue

                if target_category in ("signal", "risk"):
                    errors.append(
                        Diagnostic(
                            message=(
                                f"Definition '{leaf.name}' (category "
                                f"'{target_category}') produces no consumable fact "
                                f"or value and cannot be referenced by '{d.name}'"
                            ),
                            severity=DiagnosticSeverity.ERROR,
                            node_name=d.name,
                            node_type="definition",
                        )
                    )

        if is_timeframe_definition(d):
            _validate_timeframe_definition(d, errors)

    valid_tf_values = {tf.value for tf in Timeframe}
    for tf in analysis.timeframes:
        if tf not in valid_tf_values:
            errors.append(
                Diagnostic(
                    message=(
                        f"Analysis '{analysis.name}' declares an invalid timeframe "
                        f"'{tf}'. Valid timeframes: {', '.join(sorted(valid_tf_values))}"
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    node_name=analysis.name,
                    node_type="analysis",
                )
            )

    if not errors:
        cycles = _detect_cycles(analysis.definitions)
        for cycle in cycles:
            arrow = " \u2192 ".join(cycle)
            errors.append(
                Diagnostic(
                    message=f"Cyclic dependency detected: {arrow}",
                    severity=DiagnosticSeverity.ERROR,
                    node_name=cycle[0],
                    node_type="cycle",
                )
            )

    for d in analysis.definitions:
        is_referenced = ref_counts.get(d.name, 0) > 0
        has_references = any(
            isinstance(leaf, ReferenceExpression)
            for p in d.parameters
            for leaf in choice_leaves(p.value)
        )
        if not is_referenced and not has_references and len(analysis.definitions) > 1:
            warnings.append(
                Diagnostic(
                    message=(
                        f"Unused definition: '{d.name}' is not referenced by any "
                        f"other definition"
                    ),
                    severity=DiagnosticSeverity.WARNING,
                    node_name=d.name,
                    node_type="definition",
                )
            )

    if errors:
        return ValidationResult(
            is_valid=False,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    return ValidationResult(
        is_valid=True,
        errors=(),
        warnings=tuple(warnings),
    )


def _validate_timeframe_definition(
    definition: Definition, errors: list[Diagnostic]
) -> None:
    resolution = None
    for p in definition.parameters:
        if p.name == "resolution":
            resolution = p
            break
    if resolution is None:
        errors.append(
            Diagnostic(
                message=(
                    f"TimeFrame definition '{definition.name}' is missing the "
                    f"required 'resolution' parameter"
                ),
                severity=DiagnosticSeverity.ERROR,
                node_name=definition.name,
                node_type="definition",
            )
        )
        return

    for leaf in choice_leaves(resolution.value):
        if isinstance(leaf, ReferenceExpression):
            errors.append(
                Diagnostic(
                    message=(
                        f"TimeFrame definition '{definition.name}' resolution must "
                        f"be a literal string, not a reference"
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    node_name=definition.name,
                    node_type="definition",
                )
            )
            continue
        if isinstance(leaf, ChoiceExpression):
            continue
        if not isinstance(leaf, LiteralExpression):
            continue
        if _coerce_timeframe(leaf.value) is None:
            errors.append(
                Diagnostic(
                    message=(
                        f"TimeFrame definition '{definition.name}' has invalid "
                        f"resolution {leaf.value!r}. Valid timeframes: "
                        f"{', '.join(sorted(tf.value for tf in Timeframe))}"
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    node_name=definition.name,
                    node_type="definition",
                )
            )


def _coerce_timeframe(value: object) -> Timeframe | None:
    if isinstance(value, Timeframe):
        return value
    if not isinstance(value, str):
        return None
    try:
        return Timeframe(value)
    except ValueError:
        return None
