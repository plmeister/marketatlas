"""Thin compilation pipeline orchestrator.

Composes the four canonical stages (backlog 051):

  AST (template) → [1 validation + registry resolution + param validation]
  → [2 template expansion] → [3 concrete AST validation]
  → [4 graph compilation]

Expansion logic lives in ``expansion.py``; IR lowering / fact-key
compilation lives in ``lowering.py``.  This module owns the ``Pipeline``
class and the ``CompilerPass`` stage abstractions.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from marketatlas.analysis.ast.diagnostics import SourceMap, with_position

# --- public re-exports (unchanged import paths for all callers) -----------
from marketatlas.analysis.ast.expansion import (  # noqa: E402
    CompilationError,
    _is_reference_param,
    _merge_default_params,
    _provider_map,
    expand,
)
from marketatlas.analysis.ast.expressions import (
    ChoiceExpression,
    LiteralExpression,
    ReferenceExpression,
    choice_leaves,
)
from marketatlas.analysis.ast.instrument import TemplateGraph
from marketatlas.analysis.ast.lexer import SourcePosition
from marketatlas.analysis.ast.lowering import (  # noqa: E402
    _ast_to_config,
)
from marketatlas.analysis.ast.models import (
    SCOPE_GROUP,
    SCOPE_INSTRUMENT,
    Analysis,
    Definition,
    Provider,
)
from marketatlas.analysis.ast.param_schema import format_type, type_compatible
from marketatlas.analysis.ast.registry import ProviderRegistry
from marketatlas.analysis.ast.validation import (
    Diagnostic,
    DiagnosticSeverity,
    validate,
)
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.strategy.loader import build_analyzers

__all__ = [
    "CompilationError",
    "CompletenessPass",
    "CompilerPass",
    "ConcreteValidationPass",
    "GraphGenerationPass",
    "ParamValidationPass",
    "Pipeline",
    "RegistryResolutionPass",
    "TemplateExpansionPass",
    "ValidationPass",
    "expand",
    "_ast_to_config",
]


def _position_diagnostics(
    diagnostics: tuple[Diagnostic, ...],
    source_map: SourceMap | None,
    *,
    parameter: str | None = None,
) -> tuple[Diagnostic, ...]:
    """Attach source positions from ``source_map`` to diagnostics (backlog 059).

    Positions are preserved where the map has an entry for the diagnostic's
    node (and, for parameter-scoped findings, the named parameter); existing
    positions are never overwritten.
    """
    if source_map is None:
        return diagnostics
    return tuple(
        with_position(
            d,
            source_map.position_for(d.node_type, d.node_name, parameter=parameter),
        )
        for d in diagnostics
    )


class CompilerPass(ABC):
    """Single compilation stage. Transforms or validates the AST."""

    @abstractmethod
    def run(self, analysis: Analysis) -> Analysis: ...

    @property
    def name(self) -> str:
        return type(self).__name__


class ValidationPass(CompilerPass):
    """Stage 1: Run semantic checks on the template AST. Raise on errors.

    An optional ``SourceMap`` (backlog 059) attaches source positions to the
    diagnostics — positions are preserved through ``CompilationError`` where
    the source is mapped, and left ``None`` otherwise.
    """

    def __init__(self, source_map: SourceMap | None = None) -> None:
        self._source_map = source_map

    def run(self, analysis: Analysis) -> Analysis:
        result = validate(analysis)
        if not result.is_valid:
            errors = _position_diagnostics(result.errors, self._source_map)
            msgs = [f"[{d.severity.value}] {d.node_name}: {d.message}" for d in errors]
            raise CompilationError(
                f"Validation failed ({len(errors)} errors):\n" + "\n".join(msgs),
                errors=errors,
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
                    scope=d.scope,
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

    def __init__(self, source_map: SourceMap | None = None) -> None:
        self._source_map = source_map

    def run(self, analysis: Analysis) -> Analysis:
        variants = expand(analysis, self._source_map)
        if len(variants) != 1:
            raise CompilationError(
                f"Template expansion produced {len(variants)} concrete analyses. "
                "A TemplateExpansionPass cannot return multiple analyses through "
                "run(); use run_all() or Pipeline.expand()."
            )
        return variants[0]

    def run_all(self, analysis: Analysis) -> tuple[Analysis, ...]:
        return expand(analysis, self._source_map)


class ConcreteValidationPass(CompilerPass):
    """Stage 3: validate a concrete (post-expansion) AST.

    Runs on each concrete AST produced by stage 2. Enforces post-expansion
    invariants on top of the standard semantic validation (backlog 038):
    * every ``ChoiceExpression`` is resolved (none remain);
    * no duplicate definition names — two choice combinations can converge on
      the same concrete definition (backlogs 051/054).
    """

    def __init__(self, source_map: SourceMap | None = None) -> None:
        self._source_map = source_map

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
        errors = list(_position_diagnostics(tuple(errors), self._source_map))
        errors.extend(result.errors)

        if errors:
            msgs = [f"[{d.severity.value}] {d.node_name}: {d.message}" for d in errors]
            raise CompilationError(
                f"Concrete AST validation failed ({len(errors)} errors):\n" + "\n".join(msgs),
                errors=tuple(errors),
                warnings=result.warnings,
            )
        return analysis


class CompletenessPass(CompilerPass):
    """Stage 1: verify every contract-declared input is supplied (backlog 084c).

    After registry resolution each definition's provider has a ``ProviderContract``
    listing the fact key names it consumes (``inputs``).  For every such input
    the definition must supply a ``ReferenceExpression`` parameter — a literal
    value is configuration, not a fact dependency.  Missing inputs surface as
    ``CompilationError`` naming the definition and the missing fact.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def run(self, analysis: Analysis) -> Analysis:
        errors: list[str] = []
        provider_categories = {p.name: p.category for p in analysis.providers}
        for d in analysis.definitions:
            category = provider_categories.get(d.provider)
            if category != "analyzer":
                continue
            contract = self._registry.contract(d.provider)
            if contract is None or not contract.inputs:
                continue
            ref_params = {
                p.name for p in d.parameters if _is_reference_param(p)
            }
            if not ref_params:
                continue
            for required_input in contract.inputs:
                if required_input not in ref_params:
                    errors.append(
                        f"definition '{d.name}' is missing required input '{required_input}'"
                    )
        if errors:
            raise CompilationError(
                "Completeness check failed:\n" + "\n".join(errors)
            )
        return analysis


class ParamValidationPass(CompilerPass):
    """Stage 1: validate definition parameters against provider metadata.

    Runs post-registry-resolution (backlog 052): every provider reference is
    concrete and default params are merged, so name/required checks see the
    full effective parameter set. Checks that parameter names are known,
    required parameters are present, and literal values are type-compatible
    with the provider's schema. Providers without a registered schema (e.g.
    AST-declared with no registry counterpart) are skipped — validation never
    false-positives on opaque constructors. A ``ChoiceExpression`` value is
    type-checked per leaf; non-literal leaves (future reference expressions)
    are accepted.
    """

    def __init__(self, registry: ProviderRegistry, source_map: SourceMap | None = None) -> None:
        self._registry = registry
        self._source_map = source_map

    def run(self, analysis: Analysis) -> Analysis:
        errors: list[Diagnostic] = []
        providers = _provider_map(analysis)

        for d in analysis.definitions:
            provider = providers.get(d.provider)
            if provider is None:
                continue
            schema = self._registry.param_schema(provider.capability)
            if not schema:
                schema = self._registry.param_schema(provider.name)
            if not schema:
                continue

            known = {spec.name: spec for spec in schema}
            declared = {p.name for p in d.parameters}

            for p in d.parameters:
                if _is_reference_param(p):
                    # A reference parameter is not a provider parameter: a
                    # TimeFrame reference fills the compile-time timeframe slot
                    # and a fact reference declares a dependency edge (backlog
                    # 061). Neither is validated against the provider schema.
                    continue
                spec = known.get(p.name)
                if spec is None:
                    known_str = ", ".join(sorted(known))
                    errors.append(
                        Diagnostic(
                            message=(
                                f"Unknown parameter '{p.name}' for definition "
                                f"'{d.name}' (provider '{provider.name}'). "
                                f"Known parameters: {known_str}"
                            ),
                            severity=DiagnosticSeverity.ERROR,
                            node_name=d.name,
                            node_type="definition",
                            position=self._parameter_position(d.name, p.name),
                        )
                    )
                    continue
                for leaf in choice_leaves(p.value):
                    if not isinstance(leaf, LiteralExpression):
                        continue
                    if not type_compatible(leaf.value, spec.expected_type):
                        errors.append(
                            Diagnostic(
                                message=(
                                    f"Parameter '{p.name}' of definition '{d.name}' "
                                    f"has value of type {type(leaf.value).__name__} but "
                                    f"provider '{provider.name}' expects "
                                    f"{format_type(spec.expected_type)}"
                                ),
                                severity=DiagnosticSeverity.ERROR,
                                node_name=d.name,
                                node_type="definition",
                                position=self._parameter_position(d.name, p.name),
                            )
                        )

            for spec in schema:
                if spec.required and spec.name not in declared:
                    errors.append(
                        Diagnostic(
                            message=(
                                f"Missing required parameter '{spec.name}' for "
                                f"definition '{d.name}' (provider '{provider.name}')"
                            ),
                            severity=DiagnosticSeverity.ERROR,
                            node_name=d.name,
                            node_type="definition",
                            position=self._definition_position(d.name),
                        )
                    )

        if errors:
            msgs = [f"[{e.severity.value}] {e.node_name}: {e.message}" for e in errors]
            raise CompilationError(
                f"Provider parameter validation failed ({len(errors)} errors):\n" + "\n".join(msgs),
                errors=tuple(errors),
            )
        return analysis

    def _definition_position(self, name: str) -> SourcePosition | None:
        if self._source_map is None:
            return None
        return self._source_map.position_for("definition", name)

    def _parameter_position(self, name: str, parameter: str) -> SourcePosition | None:
        if self._source_map is None:
            return None
        return self._source_map.position_for("definition", name, parameter=parameter)


class GraphGenerationPass(CompilerPass):
    """Stage 4: Convert a concrete AST to an AnalysisGraph."""

    def run(self, analysis: Analysis) -> Analysis:
        config = _ast_to_config(analysis)
        analyzers = build_analyzers(config)
        return AnalysisGraph(analyzers)  # type: ignore[return-value]


class Pipeline:
    """Compilation pipeline over the four canonical stages (backlog 051).

    ``AST (template) → [1 AST validation + registry resolution + provider
    param validation] → [2 template expansion] → [3 concrete AST validation]
    → [4 graph compilation]``. ``add_pass`` registers the single-output
    stage-1 passes (validation, registry resolution, param validation); the
    remaining stages are orchestrated by the pipeline methods because
    expansion forks one template into many concrete ASTs.

    The ``Parse`` stage (DSL text → template AST) sits upstream of stage 1
    (backlog 057). An optional ``SourceMap`` (backlog 059) threads source
    positions into the stage-2/3 passes so expansion and concrete-validation
    errors stay located.
    """

    def __init__(self, source_map: SourceMap | None = None) -> None:
        self._passes: list[CompilerPass] = []
        self._source_map = source_map

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
        variants = TemplateExpansionPass(self._source_map).run_all(template)
        return tuple(ConcreteValidationPass(self._source_map).run(v) for v in variants)

    def compile_all(self, analysis: Analysis) -> tuple[AnalysisGraph, ...]:
        """Run the full pipeline (stages 1-4) for every concrete AST.

        Multiple concrete graphs are returned explicitly — never silently
        merged into one graph; merge semantics belong to the caller (see
        ``StrategyBundle``).
        """
        return tuple(self._graph(v) for v in self.expand(analysis))

    def compile_template(self, analysis: Analysis) -> TemplateGraph:
        """Stages 1-3 + config: compile to an instrument-neutral template.

        The single-concrete-AST entry point for backlog 063: the resulting
        ``TemplateGraph`` holds the recipe (concrete ``Analysis`` +
        ``StrategyConfig``) and materializes fresh, isolated per-instrument
        graphs via ``instantiate``. Multi-output templates raise — use
        ``compile_templates``.
        """
        variants = self.expand(analysis)
        if len(variants) != 1:
            raise CompilationError(
                f"Template expansion produced {len(variants)} concrete analyses. "
                "Pipeline.compile_template requires a single concrete AST; use "
                "Pipeline.compile_templates for multi-output templates."
            )
        concrete = variants[0]
        return TemplateGraph(
            concrete,
            _ast_to_config(concrete, scopes=frozenset({SCOPE_INSTRUMENT})),
            group_config=_ast_to_config(concrete, scopes=frozenset({SCOPE_GROUP})),
        )

    def compile_templates(self, analysis: Analysis) -> tuple[TemplateGraph, ...]:
        """Compile every concrete AST to its own instrument-neutral template.

        Multi-output path for choice templates: one ``TemplateGraph`` per
        concrete AST (backlog 063), matching the explicit multi-return
        convention of ``compile_all``.
        """
        return tuple(
            TemplateGraph(
                v,
                _ast_to_config(v, scopes=frozenset({SCOPE_INSTRUMENT})),
                group_config=_ast_to_config(v, scopes=frozenset({SCOPE_GROUP})),
            )
            for v in self.expand(analysis)
        )

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
