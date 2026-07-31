from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from marketatlas.analysis.ast.clone import clone, clone_expression
from marketatlas.analysis.ast.expressions import (
    ChoiceExpression,
    Expression,
    LiteralExpression,
)
from marketatlas.analysis.ast.models import Analysis, Definition, Parameter, Provider
from marketatlas.analysis.ast.registry import ProviderRegistry
from marketatlas.analysis.ast.validation import (
    Diagnostic,
    DiagnosticSeverity,
    validate,
)
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.strategy.config import (
    AnalyzerConfig,
    RiskConfig,
    SignalConfig,
    StrategyConfig,
)
from marketatlas.strategy.loader import build_analyzers

_T = TypeVar("_T")


class CompilerPass(ABC):
    """Single compilation stage. Transforms or validates the AST."""

    @abstractmethod
    def run(self, analysis: Analysis) -> Analysis: ...

    @property
    def name(self) -> str:
        return type(self).__name__


class ValidationPass(CompilerPass):
    """Stage 1: Run semantic checks on the template AST. Raise on errors."""

    def run(self, analysis: Analysis) -> Analysis:
        result = validate(analysis)
        if not result.is_valid:
            msgs = [f"[{d.severity.value}] {d.node_name}: {d.message}" for d in result.errors]
            raise CompilationError(
                f"Validation failed ({len(result.errors)} errors):\n" + "\n".join(msgs),
                errors=result.errors,
                warnings=result.warnings,
            )
        return analysis


class RegistryResolutionPass(CompilerPass):
    """Stage 1: Resolve symbolic provider names to concrete providers.

    Also the single owner of default-parameter merging: every resolved
    provider's ``default_params`` are inlined here for any parameter a
    definition does not declare. No later stage re-merges defaults.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def run(self, analysis: Analysis) -> Analysis:
        provider_map = _provider_map(analysis)
        resolved_providers: dict[str, Provider] = dict(provider_map)
        resolved_defs: list[Definition] = []

        for d in analysis.definitions:
            provider_name = d.provider

            try:
                resolved = self._registry.resolve(provider_name)
                resolved_providers[resolved.name] = resolved
                provider_name = resolved.name
            except LookupError:
                if provider_name not in provider_map:
                    raise CompilationError(
                        f"Provider '{d.provider}' not found for definition '{d.name}'. "
                        "Neither in AST providers nor in registry."
                    ) from None

            provider = resolved_providers[provider_name]
            merged_params = _merge_default_params(provider, d.parameters)
            resolved_defs.append(
                Definition(
                    name=d.name,
                    provider=provider_name,
                    parameters=merged_params,
                    bindings=d.bindings,
                    id=d.id,
                    metadata=d.metadata,
                )
            )

        return Analysis(
            name=analysis.name,
            version=analysis.version,
            definitions=tuple(resolved_defs),
            providers=tuple(resolved_providers.values()),
            id=analysis.id,
            metadata=analysis.metadata,
        )


class TemplateExpansionPass(CompilerPass):
    """Stage 2: expand template choices into concrete ASTs.

    Choice expansion is a fork (one template → N concrete ASTs), so the
    single-output ``run`` interface only handles choice-free templates
    (identity). Use ``run_all`` (or ``Pipeline.expand``) to obtain every
    concrete variant (backlog 050).
    """

    def run(self, analysis: Analysis) -> Analysis:
        variants = expand(analysis)
        if len(variants) != 1:
            raise CompilationError(
                f"Template expansion produced {len(variants)} concrete analyses. "
                "A TemplateExpansionPass cannot return multiple analyses through "
                "run(); use run_all() or Pipeline.expand()."
            )
        return variants[0]

    def run_all(self, analysis: Analysis) -> tuple[Analysis, ...]:
        return expand(analysis)


class ConcreteValidationPass(CompilerPass):
    """Stage 3: validate a concrete (post-expansion) AST.

    Runs on each concrete AST produced by stage 2. Enforces post-expansion
    invariants on top of the standard semantic validation (backlog 038):
    * every ``ChoiceExpression`` is resolved (none remain);
    * no duplicate definition names — two choice combinations can converge on
      the same concrete definition (backlogs 051/054).
    """

    def run(self, analysis: Analysis) -> Analysis:
        errors: list[Diagnostic] = []

        for d in analysis.definitions:
            for p in d.parameters:
                if isinstance(p.value, ChoiceExpression):
                    errors.append(
                        Diagnostic(
                            message=(
                                f"Unresolved ChoiceExpression for parameter "
                                f"'{p.name}' of definition '{d.name}'. Template "
                                f"expansion must replace every choice before "
                                f"concrete validation."
                            ),
                            severity=DiagnosticSeverity.ERROR,
                            node_name=d.name,
                            node_type="definition",
                        )
                    )

        seen: set[str] = set()
        for d in analysis.definitions:
            if d.name in seen:
                errors.append(
                    Diagnostic(
                        message=(
                            f"Duplicate definition '{d.name}' after template "
                            f"expansion. Two choice combinations produced the "
                            f"same concrete definition."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        node_name=d.name,
                        node_type="definition",
                    )
                )
            seen.add(d.name)

        result = validate(analysis)
        errors.extend(result.errors)

        if errors:
            msgs = [f"[{d.severity.value}] {d.node_name}: {d.message}" for d in errors]
            raise CompilationError(
                f"Concrete AST validation failed ({len(errors)} errors):\n" + "\n".join(msgs),
                errors=tuple(errors),
                warnings=result.warnings,
            )
        return analysis


class GraphGenerationPass(CompilerPass):
    """Stage 4: Convert a concrete AST to an AnalysisGraph."""

    def run(self, analysis: Analysis) -> Analysis:
        config = _ast_to_config(analysis)
        analyzers = build_analyzers(config)
        return AnalysisGraph(analyzers)  # type: ignore[return-value]


@dataclass(frozen=True)
class CompilationError(Exception):
    message: str = ""
    errors: tuple[Diagnostic, ...] = field(default_factory=tuple)
    warnings: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return self.message


class Pipeline:
    """Compilation pipeline over the four canonical stages (backlog 051).

    ``AST (template) → [1 AST validation] → [2 template expansion] →
    [3 concrete AST validation] → [4 graph compilation]``. ``add_pass``
    registers the single-output stage-1 passes (validation, registry
    resolution); the remaining stages are orchestrated by the pipeline
    methods because expansion forks one template into many concrete ASTs.

    The ``Parse`` stage (DSL text → template AST) sits upstream of stage 1
    (backlog 057).
    """

    def __init__(self) -> None:
        self._passes: list[CompilerPass] = []

    def add_pass(self, pass_: CompilerPass) -> Pipeline:
        self._passes.append(pass_)
        return self

    def run_to_ast(self, analysis: Analysis) -> Analysis:
        """Run the registered stage-1 passes; stop before graph generation."""
        current = analysis
        for pass_ in self._passes:
            result = pass_.run(current)
            if isinstance(result, AnalysisGraph):
                return current
            current = result
        return current

    def expand(self, analysis: Analysis) -> tuple[Analysis, ...]:
        """Stages 1-3: validate/resolve the template, expand choices, then
        validate each concrete AST. Returns every concrete AST."""
        template = self.run_to_ast(analysis)
        variants = TemplateExpansionPass().run_all(template)
        return tuple(ConcreteValidationPass().run(v) for v in variants)

    def compile_all(self, analysis: Analysis) -> tuple[AnalysisGraph, ...]:
        """Run the full pipeline (stages 1-4) for every concrete AST.

        Multiple concrete graphs are returned explicitly — never silently
        merged into one graph; merge semantics belong to the caller (see
        ``StrategyBundle``).
        """
        return tuple(self._graph(v) for v in self.expand(analysis))

    def run(self, analysis: Analysis) -> AnalysisGraph:
        """Run the full pipeline for a single concrete AST.

        Works only when template expansion yields exactly one concrete AST
        (choice-free templates). Multi-output templates raise — use
        ``compile_all`` for multi-output compilation or ``expand`` for the
        concrete ASTs.
        """
        variants = self.expand(analysis)
        if len(variants) != 1:
            raise CompilationError(
                f"Template expansion produced {len(variants)} concrete analyses. "
                "Pipeline.run requires a single concrete AST; use "
                "Pipeline.compile_all for multi-output compilation or "
                "Pipeline.expand for the concrete ASTs."
            )
        return self._graph(variants[0])

    def _graph(self, analysis: Analysis) -> AnalysisGraph:
        result = GraphGenerationPass().run(analysis)
        if not isinstance(result, AnalysisGraph):
            raise CompilationError(
                f"GraphGenerationPass returned unexpected type: {type(result).__name__}"
            )
        return result


def _provider_map(analysis: Analysis) -> dict[str, Provider]:
    return {p.name: p for p in analysis.providers}


def _merge_default_params(
    provider: Provider, params: tuple[Parameter, ...]
) -> tuple[Parameter, ...]:
    existing = {p.name for p in params}
    merged = list(params)
    for dp in provider.default_params:
        if dp.name not in existing:
            merged.append(dp)
    return tuple(merged)


def _choice_leaves(expr: Expression) -> tuple[Expression, ...]:
    """Flatten a ``ChoiceExpression`` into its non-choice leaf values.

    Nested choices are flattened recursively: ``Choice([Choice([1, 2]), 3])``
    yields leaves ``(Literal(1), Literal(2), Literal(3))``. Non-choice
    expressions return a single-element tuple.
    """
    if isinstance(expr, ChoiceExpression):
        leaves: list[Expression] = []
        for value in expr.values:
            leaves.extend(_choice_leaves(value))
        return tuple(leaves)
    return (expr,)


def _cartesian(options: Sequence[Sequence[_T]]) -> list[tuple[_T, ...]]:
    """Deterministic cartesian product in declaration order.

    The rightmost sequence varies fastest (column-major): product of
    ``(a, b) x (1, 2)`` yields ``(a,1), (a,2), (b,1), (b,2)``.
    """
    result: list[tuple[_T, ...]] = [()]
    for opts in options:
        result = [prev + (opt,) for prev in result for opt in opts]
    return result


def _expand_definition(defn: Definition) -> tuple[tuple[Parameter, ...], ...]:
    """Produce one parameter-variant tuple per cartesian combination of choices.

    Each parameter with a ``ChoiceExpression`` value contributes one option per
    flattened leaf; literal and other-expression params contribute a single
    option. An empty choice raises ``CompilationError`` naming the definition
    and parameter. Every returned parameter carries a freshly cloned value.
    """
    options: list[tuple[Expression, ...]] = []
    for p in defn.parameters:
        leaves = _choice_leaves(p.value)
        if isinstance(p.value, ChoiceExpression) and not leaves:
            raise CompilationError(
                f"Empty choice for parameter '{p.name}' of definition "
                f"'{defn.name}'. A ChoiceExpression must have at least one value."
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


def expand(analysis: Analysis) -> tuple[Analysis, ...]:
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

    Raises ``CompilationError`` on an empty ``ChoiceExpression``.
    """
    template = clone(analysis)
    variants_per_def = [_expand_definition(d) for d in template.definitions]
    combos = _cartesian(variants_per_def)
    return tuple(
        Analysis(
            name=template.name,
            version=template.version,
            definitions=tuple(
                Definition(
                    name=d.name,
                    provider=d.provider,
                    parameters=params,
                    bindings=d.bindings,
                    id=d.id,
                    metadata=d.metadata,
                )
                for d, params in zip(template.definitions, combo)
            ),
            providers=template.providers,
            id=template.id,
            metadata=template.metadata,
        )
        for combo in combos
    )


def _ast_to_config(analysis: Analysis) -> StrategyConfig:
    providers = _provider_map(analysis)
    analyzer_configs: list[AnalyzerConfig] = []
    signal_configs: list[SignalConfig] = []
    risk_config: RiskConfig = RiskConfig(algorithm="none")

    for d in analysis.definitions:
        provider = providers.get(d.provider)
        if provider is None:
            raise CompilationError(f"Unknown provider: {d.provider}")

        params: dict[str, object] = {}
        for p in d.parameters:
            value: object = p.value
            if isinstance(value, LiteralExpression):
                value = value.value
            elif isinstance(value, ChoiceExpression):
                raise CompilationError(
                    f"Parameter '{p.name}' of definition '{d.name}' is a "
                    f"ChoiceExpression and cannot be compiled until expanded "
                    f"(template expansion, backlog 050)."
                )
            elif isinstance(value, Expression):
                raise CompilationError(
                    f"Non-literal expression for parameter '{p.name}' of definition "
                    f"'{d.name}' cannot be compiled yet: {type(value).__name__}"
                )
            params[p.name] = value

        if provider.category == "analyzer":
            analyzer_configs.append(AnalyzerConfig(type=provider.impl, params=params))
        elif provider.category == "signal":
            requires = tuple(b.output for b in d.bindings)
            signal_configs.append(SignalConfig(type=provider.impl, requires=requires, rules=params))
        elif provider.category == "risk":
            risk_config = RiskConfig(algorithm=provider.impl, params=params)

    return StrategyConfig(
        name=analysis.name,
        version=analysis.version,
        analyzers=tuple(analyzer_configs),
        signals=tuple(signal_configs),
        risk=risk_config,
    )
