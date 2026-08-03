from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from marketatlas.analysis.ast.lexer import SourcePosition
from marketatlas.analysis.ast.models import Analysis, Definition
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


def _detect_cycles(definitions: Sequence[Definition]) -> list[list[str]]:
    name_to_idx: dict[str, int] = {}
    for i, d in enumerate(definitions):
        name_to_idx[d.name] = i

    adjacency: list[list[int]] = [[] for _ in range(len(definitions))]
    for d in definitions:
        if d.name not in name_to_idx:
            continue
        t_idx = name_to_idx[d.name]
        for b in d.bindings:
            if b.source in name_to_idx:
                src_idx = name_to_idx[b.source]
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


def validate(analysis: Analysis) -> ValidationResult:
    errors: list[Diagnostic] = []
    warnings: list[Diagnostic] = []

    provider_names = {p.name for p in analysis.providers}
    def_names = {d.name for d in analysis.definitions}

    seen_names: set[str] = set()
    ref_counts: dict[str, int] = {}
    has_bindings: set[str] = set()

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

        if d.timeframe is not None and not isinstance(d.timeframe, Timeframe):
            errors.append(
                Diagnostic(
                    message=(
                        f"Definition '{d.name}' has an invalid timeframe "
                        f"'{d.timeframe}'. Valid timeframes: "
                        f"{', '.join(tf.value for tf in Timeframe)}"
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    node_name=d.name,
                    node_type="definition",
                )
            )

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

        for b in d.bindings:
            if b.source == b.target:
                errors.append(
                    Diagnostic(
                        message=f"Self-referencing binding: " f"'{b.source}' binds to itself",
                        severity=DiagnosticSeverity.ERROR,
                        node_name=d.name,
                        node_type="definition",
                    )
                )

            if b.source not in def_names:
                errors.append(
                    Diagnostic(
                        message=f"Unknown source definition in binding: " f"'{b.source}'",
                        severity=DiagnosticSeverity.ERROR,
                        node_name=d.name,
                        node_type="definition",
                    )
                )
            else:
                ref_counts[b.source] = ref_counts.get(b.source, 0) + 1

            if b.target not in def_names:
                errors.append(
                    Diagnostic(
                        message=f"Unknown target definition in binding: " f"'{b.target}'",
                        severity=DiagnosticSeverity.ERROR,
                        node_name=d.name,
                        node_type="definition",
                    )
                )

            if d.name in def_names:
                has_bindings.add(d.name)

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
        is_active = is_referenced or d.name in has_bindings
        if not is_active and len(analysis.definitions) > 1:
            warnings.append(
                Diagnostic(
                    message=f"Unused definition: '{d.name}' " f"is not referenced by any binding",
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
