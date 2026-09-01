"""IR lowering and fact-key compilation — reference→key mapping, bindings injection.

Converts a concrete AST into ``StrategyConfig`` (``_ast_to_config``) and
resolves reference parameters into compile-time timeframe / binding / requires
entries (backlog 062).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from marketatlas.analysis.ast.expansion import (
    CompilationError,
    _provider_map,
)
from marketatlas.analysis.ast.expressions import (
    ChoiceExpression,
    LiteralExpression,
    ReferenceExpression,
    SpanningReferenceExpression,
)
from marketatlas.analysis.ast.models import (
    SCOPE_GROUP,
    Analysis,
    Definition,
    Provider,
    is_timeframe_definition,
)
from marketatlas.analysis.ast.registry import create_default_registry
from marketatlas.data.types import Timeframe
from marketatlas.strategy.config import (
    AnalyzerConfig,
    RiskConfig,
    SignalConfig,
    StrategyConfig,
)


@dataclass(frozen=True)
class _ResolvedReference:
    """Compile-time interpretation of a reference parameter (backlog 062).

    A reference resolves to exactly one of three things:
    * ``timeframe`` — value substitution: a ``TimeFrame`` definition fills the
      consumer's ``AnalyzerConfig.timeframe`` slot (backlog 061);
    * ``binding`` — an analyzer or risk fact dependency: the consumed fact name
      with an explicit ``name@timeframe`` suffix when it crosses timeframes (or
      whenever the source timeframe is known), injected into the consumer's
      ``bindings`` so it resolves the right ``FactKey``;
    * ``requires`` — a signal fact dependency: the consumed fact name, carrying
      the source timeframe suffix for cross-timeframe references.
    A reference on an opaque consumer (risk) resolves to a binding (backlog 083).
    """

    timeframe: str | None = None
    binding: str | None = None
    requires: str | None = None


def _resolved_definition_timeframe(
    definition: Definition, def_by_name: dict[str, Definition]
) -> str | None:
    """The compile-time timeframe a definition declares (backlog 061/062).

    ``None`` means "strategy base timeframe". Only analyzer definitions may
    reference a ``TimeFrame`` definition; the reference-slot field is always
    ``timeframe``.
    """
    for p in definition.parameters:
        if not isinstance(p.value, ReferenceExpression):
            continue
        target = def_by_name.get(p.value.name)
        if target is not None and is_timeframe_definition(target):
            return _resolution_value(target)
    return None


def _resolve_reference(
    param_name: str,
    reference: ReferenceExpression,
    def_by_name: dict[str, Definition],
    def_timeframes: dict[str, str | None],
    providers: dict[str, Provider],
    provider: Provider,
    owner: str,
    base_tf: str | None,
) -> _ResolvedReference:
    """Resolve a reference parameter to its compile-time interpretation.

    A reference to a ``TimeFrame`` definition is value substitution (backlog
    061). A reference to a fact-producing definition is a dependency edge: on
    an analyzer it becomes a ``bindings`` override carrying the source
    timeframe when the reference crosses timeframes; on a signal it becomes a
    ``requires`` entry with the source timeframe suffix; on a risk node it
    becomes a ``bindings`` override carrying the source timeframe (backlog
    083). References are always explicit declarations in the DSL — a consumer
    at ``1d`` referencing a producer at ``1w`` is declared by the reference
    itself, so no separate cross-timeframe opt-in exists (the fallback, an
    undeclared cross-timeframe dependency, fails loudly at graph construction
    as an unsatisfied dependency).
    """
    target = def_by_name.get(reference.name)
    if target is None:
        raise CompilationError(
            f"Unknown reference: definition '{owner}' references '{reference.name}'"
        )
    if is_timeframe_definition(target):
        if isinstance(reference, SpanningReferenceExpression):
            raise CompilationError(
                f"Spanning reference to TimeFrame definition '{reference.name}' on "
                f"'{owner}' is invalid: a timeframe is a compile-time value, not a "
                f"per-member fact"
            )
        if provider.category != "analyzer":
            raise CompilationError(
                f"Reference to TimeFrame definition '{reference.name}' on '{owner}' "
                f"is only valid on analyzer definitions, not '{provider.category}'"
            )
        return _ResolvedReference(timeframe=_resolution_value(target))

    source_tf = def_timeframes.get(target.name) or base_tf
    if isinstance(reference, SpanningReferenceExpression):
        if provider.category != "analyzer":
            raise CompilationError(
                f"Spanning reference on '{owner}' is only valid on analyzer "
                f"definitions, not '{provider.category}'"
            )
        _check_fact_declared(param_name, target, source_tf, providers, owner)
        # The binding is member-agnostic at compile time: the group node names
        # the consumed fact per member only at instantiation, so the binding
        # must always carry the source timeframe to disambiguate member facts
        # across timeframes (backlog 064). ``"1d"`` is the strategy base
        # default when neither the member nor the analysis declares one.
        return _ResolvedReference(binding=f"{param_name}@{source_tf or '1d'}")
    if provider.category == "analyzer":
        _check_fact_declared(param_name, target, source_tf, providers, owner)
        consumer_tf = _resolved_definition_timeframe(def_by_name[owner], def_by_name) or base_tf
        key = (
            param_name
            if source_tf is None or source_tf == consumer_tf
            else f"{param_name}@{source_tf}"
        )
        return _ResolvedReference(binding=key)
    if provider.category == "signal":
        if source_tf is None or source_tf == base_tf:
            entry = param_name
        else:
            entry = f"{param_name}@{source_tf}"
        return _ResolvedReference(requires=entry)
    if provider.category == "risk":
        _check_fact_declared(param_name, target, source_tf, providers, owner)
        # The reference param names the consumed fact; the binding carries the
        # source-timeframe suffix whenever one is known so a name shared across
        # timeframes (e.g. ``swing@1d`` vs ``swing@1w``) resolves unambiguously.
        binding = param_name if source_tf is None else f"{param_name}@{source_tf}"
        return _ResolvedReference(binding=binding)
    return _ResolvedReference()


def _check_fact_declared(
    field: str,
    target: Definition,
    source_tf: str | None,
    providers: dict[str, Provider],
    owner: str,
) -> None:
    """Verify the consumed fact name is produced by the referenced definition.

    Instantiates the target's analyzer with its declared (literal) parameters
    at the source timeframe and reads ``produces()`` — precise for
    parameterised fact names like ``ema_50`` where a static contract cannot
    know the effective name (backlog 058 contracts are derived with default
    args). Opaque providers (no analyzer class) are skipped rather than
    false-positive.
    """
    provider = providers.get(target.provider)
    if provider is None:
        return
    cls = create_default_registry().analyzer_classes().get(provider.impl)
    if cls is None:
        return
    params: dict[str, Any] = {}
    for p in target.parameters:
        if isinstance(p.value, LiteralExpression):
            params[p.name] = p.value.value
    if source_tf is not None:
        params["timeframe"] = source_tf
    try:
        instance = cls(**params)
    except Exception:
        return
    produced = {str(fk.name) for fk in instance.produces()}
    if field not in produced:
        known = ", ".join(sorted(produced)) if produced else "(none)"
        raise CompilationError(
            f"Reference to '{field}' from '{owner}' is not declared by provider "
            f"'{target.provider}': definition '{target.name}' produces {known}"
        )


def _ast_to_config(analysis: Analysis, *, scopes: frozenset[str] | None = None) -> StrategyConfig:
    """Convert a concrete AST to a ``StrategyConfig``.

    By default every definition flows into the config. ``scopes`` filters to a
    subset of node scopes (backlog 064): the per-instrument config
    (``{instrument}``) excludes group nodes and the group config
    (``{group}``) contains only group nodes — the runtime supplies the member
    list, so group bindings stay member-agnostic here and the ``members``
    parameter is injected at instantiation.
    """
    providers = _provider_map(analysis)
    def_by_name = {d.name: d for d in analysis.definitions}
    if scopes is None:
        group_names = [d.name for d in analysis.definitions if d.scope == SCOPE_GROUP]
        if group_names:
            listed = ", ".join(group_names)
            raise CompilationError(
                f"Analysis '{analysis.name}' has group-scoped definitions ({listed}) "
                "which cannot compile to a single graph. Use "
                "Pipeline.compile_template + instantiate_group: group nodes need "
                "the runtime member list (backlog 064)."
            )
    analyzer_configs: list[AnalyzerConfig] = []
    signal_configs: list[SignalConfig] = []
    risk_config: RiskConfig = RiskConfig(algorithm="none")
    base_tf = analysis.timeframes[0] if analysis.timeframes else None

    def_timeframes = {
        d.name: _resolved_definition_timeframe(d, def_by_name) for d in analysis.definitions
    }

    for d in analysis.definitions:
        if scopes is not None and d.scope not in scopes:
            continue
        provider = providers.get(d.provider)
        if provider is None:
            raise CompilationError(f"Unknown provider: {d.provider}")

        params: dict[str, object] = {}
        requires: list[str] = []
        timeframe: str | None = None
        bindings: dict[str, str] = {}

        for p in d.parameters:
            value: object = p.value
            if isinstance(value, ReferenceExpression):
                resolved = _resolve_reference(
                    p.name,
                    value,
                    def_by_name,
                    def_timeframes,
                    providers,
                    provider,
                    d.name,
                    base_tf,
                )
                if resolved.timeframe is not None:
                    timeframe = resolved.timeframe
                if resolved.requires is not None:
                    requires.append(resolved.requires)
                if resolved.binding is not None:
                    bindings[p.name] = resolved.binding
                continue
            if isinstance(value, LiteralExpression):
                params[p.name] = value.value
            elif isinstance(value, ChoiceExpression):
                raise CompilationError(
                    f"Parameter '{p.name}' of definition '{d.name}' is a "
                    f"ChoiceExpression and cannot be compiled until expanded "
                    f"(template expansion, backlog 050)."
                )
            else:
                raise CompilationError(
                    f"Non-literal expression for parameter '{p.name}' of definition "
                    f"'{d.name}' cannot be compiled yet: {type(value).__name__}"
                )

        if bindings:
            params["bindings"] = bindings

        if provider.category == "analyzer":
            analyzer_configs.append(
                AnalyzerConfig(
                    type=provider.impl,
                    params=params,
                    timeframe=timeframe if timeframe is not None else base_tf,
                )
            )
        elif provider.category == "signal":
            signal_configs.append(
                SignalConfig(type=provider.impl, requires=tuple(requires), rules=params)
            )
        elif provider.category == "risk":
            risk_config = RiskConfig(algorithm=provider.impl, params=params)

    config = StrategyConfig(
        name=analysis.name,
        version=analysis.version,
        analyzers=tuple(analyzer_configs),
        signals=tuple(signal_configs),
        risk=risk_config,
    )
    if analysis.timeframes:
        config = StrategyConfig(
            name=config.name,
            version=config.version,
            timeframes=analysis.timeframes,
            analyzers=config.analyzers,
            signals=config.signals,
            risk=config.risk,
        )
    return config


def _resolution_value(target: Definition) -> str:
    for p in target.parameters:
        if p.name == "resolution":
            value = p.value.value if isinstance(p.value, LiteralExpression) else p.value
            tf = _coerce_timeframe(value)
            if tf is None:
                raise CompilationError(
                    f"TimeFrame definition '{target.name}' has invalid resolution " f"{value!r}"
                )
            return tf.value
    raise CompilationError(
        f"TimeFrame definition '{target.name}' is missing the 'resolution' parameter"
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
