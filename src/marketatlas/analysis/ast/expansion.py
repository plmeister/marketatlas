"""DSL expansion — pattern matching, choice-variant generation, macro expansion.

Pure transformation: one template AST → N concrete ASTs (backlog 050).
No compilation or fact-key logic lives here.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from marketatlas.analysis.ast.clone import clone, clone_expression
from marketatlas.analysis.ast.diagnostics import SourceMap
from marketatlas.analysis.ast.expressions import (
    ChoiceExpression,
    Expression,
    ReferenceExpression,
    choice_leaves,
)
from marketatlas.analysis.ast.models import (
    Analysis,
    Definition,
    Parameter,
    Provider,
    derive_timeframes,
)
from marketatlas.analysis.ast.validation import Diagnostic, DiagnosticSeverity

_T = TypeVar("_T")


@dataclass(frozen=True)
class CompilationError(Exception):
    message: str = ""
    errors: tuple[Diagnostic, ...] = field(default_factory=tuple)
    warnings: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return self.message


CompilationError.__init_subclass__ = None  # type: ignore[assignment]


# Allow exception machinery to set traceback/context fields on frozen dataclass
_orig_setattr = CompilationError.__setattr__


def _compilation_error_setattr(self: CompilationError, name: str, value: object) -> None:
    if name in ("__traceback__", "__context__", "__cause__", "__suppress_context__"):
        object.__setattr__(self, name, value)
    else:
        _orig_setattr(self, name, value)


CompilationError.__setattr__ = _compilation_error_setattr  # type: ignore[assignment]


def _provider_map(analysis: Analysis) -> dict[str, Provider]:
    return {p.name: p for p in analysis.providers}


def _is_reference_param(param: Parameter) -> bool:
    """Whether a parameter value references a definition (backlog 061)."""
    return any(isinstance(leaf, ReferenceExpression) for leaf in choice_leaves(param.value))


def _merge_default_params(
    provider: Provider, params: tuple[Parameter, ...]
) -> tuple[Parameter, ...]:
    existing = {p.name for p in params}
    merged = list(params)
    for dp in provider.default_params:
        if dp.name not in existing:
            merged.append(dp)
    return tuple(merged)


def _cartesian(options: Sequence[Sequence[_T]]) -> list[tuple[_T, ...]]:
    """Deterministic cartesian product in declaration order.

    The rightmost sequence varies fastest (column-major): product of
    ``(a, b) x (1, 2)`` yields ``(a,1), (a,2), (b,1), (b,2)``.
    """
    result: list[tuple[_T, ...]] = [()]
    for opts in options:
        result = [prev + (opt,) for prev in result for opt in opts]
    return result


def _expand_definition(
    defn: Definition, source_map: SourceMap | None = None
) -> tuple[tuple[Parameter, ...], ...]:
    """Produce one parameter-variant tuple per cartesian combination of choices.

    Each parameter with a ``ChoiceExpression`` value contributes one option per
    flattened leaf; literal and other-expression params contribute a single
    option. An empty choice raises ``CompilationError`` naming the definition
    and parameter (positioned when ``source_map`` provides one). Every returned
    parameter carries a freshly cloned value.
    """
    options: list[tuple[Expression, ...]] = []
    for p in defn.parameters:
        leaves = choice_leaves(p.value)
        if isinstance(p.value, ChoiceExpression) and not leaves:
            position = (
                source_map.position_for("definition", defn.name, parameter=p.name)
                if source_map is not None
                else None
            )
            raise CompilationError(
                f"Empty choice for parameter '{p.name}' of definition "
                f"'{defn.name}'. A ChoiceExpression must have at least one value.",
                errors=(
                    Diagnostic(
                        message=(
                            f"Empty choice for parameter '{p.name}' of definition "
                            f"'{defn.name}'. A ChoiceExpression must have at least "
                            f"one value."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        node_name=defn.name,
                        node_type="definition",
                        position=position,
                    ),
                ),
            )
        options.append(leaves)

    combos = _cartesian(options)
    return tuple(
        tuple(
            Parameter(name=p.name, value=clone_expression(value))
            for p, value in zip(defn.parameters, combo)
        )
        for combo in combos
    )


def expand(analysis: Analysis, source_map: SourceMap | None = None) -> tuple[Analysis, ...]:
    """Expand an AST template into concrete ASTs with literal-only parameters.

    Every ``ChoiceExpression`` parameter (backlog 048) is replaced by its
    leaves; choices across parameters and definitions combine by cartesian
    product. Nested choices are flattened into the product. ``list`` literal
    params are ordinary values and never expand. The input template is never
    mutated — each variant is built from a deep clone (backlog 049).

    Ordering is deterministic: parameter choices iterate in declaration order
    with the rightmost choice varying fastest; definitions preserve template
    order. Expansion count can explode (product of all choice sizes) — callers
    should treat the result as a set of concrete templates, not rely on it
    staying small.

    Convergent choices (two combinations producing an equal AST) are *not*
    deduplicated here; stage-3 concrete-AST validation (backlogs 051/054)
    reports the resulting duplicate definitions.

    Raises ``CompilationError`` on an empty ``ChoiceExpression`` (positioned
    when ``source_map`` supplies one).
    """
    template = clone(analysis)
    variants_per_def = [_expand_definition(d, source_map) for d in template.definitions]
    combos = _cartesian(variants_per_def)
    return tuple(
        Analysis(
            name=template.name,
            version=template.version,
            definitions=_variant_definitions(template.definitions, combo),
            providers=template.providers,
            timeframes=_variant_timeframes(template.definitions, combo),
            id=template.id,
            metadata=template.metadata,
        )
        for combo in combos
    )


def _variant_definitions(
    template: Sequence[Definition], combo: tuple[tuple[Parameter, ...], ...]
) -> tuple[Definition, ...]:
    return tuple(
        Definition(
            name=d.name,
            provider=d.provider,
            parameters=params,
            scope=d.scope,
            id=d.id,
            metadata=d.metadata,
        )
        for d, params in zip(template, combo)
    )


def _variant_timeframes(
    template: Sequence[Definition], combo: tuple[tuple[Parameter, ...], ...]
) -> tuple[str, ...]:
    return derive_timeframes(_variant_definitions(template, combo))
