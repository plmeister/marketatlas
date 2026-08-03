from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from marketatlas.analysis.ast.expressions import (
    Choice,
    LiteralExpression,
    choice_leaves,
    wrap,
)
from marketatlas.analysis.ast.models import (
    Analysis,
    Definition,
    Parameter,
    Provider,
    derive_timeframes,
)
from marketatlas.analysis.ast.param_schema import ParamSpec, format_type, type_compatible
from marketatlas.analysis.ast.registry import ProviderRegistry, create_default_registry

__all__ = [
    "ATR",
    "Choice",
    "DetectPullback",
    "EMA",
    "GenerateSignal",
    "ManageRisk",
    "ProviderConstructionError",
    "SR",
    "SwingStructure",
    "Swings",
    "Trend",
    "build_analysis",
    "construct",
]


class ProviderConstructionError(ValueError):
    """Invalid kwargs passed to a provider factory.

    Mirrors the provider param schema validation (backlog 052) at
    construction time, but raises immediately with the provider name instead
    of accumulating ``Diagnostic`` objects.
    """


def construct(
    capability: str,
    name: str | None = None,
    *,
    registry: ProviderRegistry | None = None,
    **params: object,
) -> Definition:
    """Build a ``Definition`` referencing the provider for ``capability``.

    Resolves ``capability`` via the default (or supplied) registry, applies
    the provider's default params (explicit kwargs override), and validates
    every parameter name/value against the provider's param schema before
    returning. Raw values are wrapped as literals (backlog 047);
    ``ChoiceExpression`` values pass through unwrapped (backlog 048) and are
    type-checked per leaf.

    Raises ``ProviderConstructionError`` for an unknown capability, an unknown
    kwarg, a missing required param, or a type-incompatible value.
    """
    reg = registry if registry is not None else create_default_registry()
    try:
        provider = reg.resolve(capability)
    except LookupError as e:
        raise ProviderConstructionError(str(e)) from None
    schema = reg.param_schema(provider.capability) or reg.param_schema(provider.name) or ()

    parameters = _merge_params(params, provider.default_params)
    _validate(parameters, schema, provider)
    return Definition(
        name=name if name is not None else capability,
        provider=capability,
        parameters=parameters,
    )


def build_analysis(
    name: str,
    definitions: Sequence[Definition],
    *,
    version: str = "1.0",
    registry: ProviderRegistry | None = None,
) -> Analysis:
    """Combine constructed definitions into a self-contained ``Analysis``.

    ``providers`` is populated from the registry so the template round-trips
    through serialization (backlog 039) and validates standalone. Each
    definition's ``provider`` field is treated as a capability key; a key the
    registry cannot resolve is kept verbatim (drop-in for manually built
    definitions). Duplicate definition names raise immediately.
    """
    reg = registry if registry is not None else create_default_registry()
    seen: set[str] = set()
    seen_providers: set[str] = set()
    providers: list[Provider] = []
    for d in definitions:
        if d.name in seen:
            raise ValueError(f"Duplicate definition name: {d.name}")
        seen.add(d.name)
        provider = _synthetic_provider(d, reg)
        if provider.name not in seen_providers:
            seen_providers.add(provider.name)
            providers.append(provider)
    return Analysis(
        name=name,
        version=version,
        definitions=tuple(definitions),
        providers=tuple(providers),
        timeframes=derive_timeframes(None, tuple(definitions)),
    )


def _synthetic_provider(definition: Definition, registry: ProviderRegistry) -> Provider:
    try:
        resolved = registry.resolve(definition.provider)
    except LookupError:
        return Provider(
            name=definition.provider,
            capability=definition.provider,
            category="analyzer",
            impl=definition.provider,
        )
    return Provider(
        name=definition.provider,
        capability=definition.provider,
        category=resolved.category,
        impl=resolved.impl,
        default_params=resolved.default_params,
    )


def _merge_params(
    params: dict[str, object], defaults: tuple[Parameter, ...]
) -> tuple[Parameter, ...]:
    merged: list[Parameter] = [Parameter(name=k, value=wrap(v)) for k, v in params.items()]
    declared = {p.name for p in merged}
    for dp in defaults:
        if dp.name not in declared:
            merged.append(dp)
    return tuple(merged)


def _validate(
    parameters: tuple[Parameter, ...],
    schema: tuple[ParamSpec, ...],
    provider: Provider,
) -> None:
    if not schema:
        return
    known = {spec.name: spec for spec in schema}
    declared: set[str] = set()

    for p in parameters:
        spec = known.get(p.name)
        if spec is None:
            known_str = ", ".join(sorted(known))
            raise ProviderConstructionError(
                f"Unknown parameter '{p.name}' for provider '{provider.capability}' "
                f"(class {provider.impl}). Known parameters: {known_str}"
            )
        declared.add(p.name)
        for leaf in choice_leaves(p.value):
            if not isinstance(leaf, LiteralExpression):
                continue
            if not type_compatible(leaf.value, spec.expected_type):
                raise ProviderConstructionError(
                    f"Parameter '{p.name}' has value of type "
                    f"{type(leaf.value).__name__} but provider '{provider.capability}' "
                    f"(class {provider.impl}) expects {format_type(spec.expected_type)}"
                )

    for spec in schema:
        if spec.required and spec.name not in declared:
            raise ProviderConstructionError(
                f"Missing required parameter '{spec.name}' for provider "
                f"'{provider.capability}' (class {provider.impl})"
            )


def EMA(  # noqa: N802
    name: str | None = None, **params: Any
) -> Definition:
    """Definition for the ``ema`` provider (default period 20 applied)."""
    return construct("ema", name, **params)


def ATR(  # noqa: N802
    name: str | None = None, **params: Any
) -> Definition:
    """Definition for the ``atr`` provider (default period 14 applied)."""
    return construct("atr", name, **params)


def Trend(  # noqa: N802
    name: str | None = None, **params: Any
) -> Definition:
    """Definition for the ``trend`` provider (default keys applied)."""
    return construct("trend", name, **params)


def SwingStructure(  # noqa: N802
    name: str | None = None, **params: Any
) -> Definition:
    """Definition for the ``swingstructure`` provider (default lookback 50)."""
    return construct("swingstructure", name, **params)


def Swings(  # noqa: N802
    name: str | None = None, **params: Any
) -> Definition:
    """Definition for the ``swings`` provider (default lookback 50)."""
    return construct("swings", name, **params)


def SR(  # noqa: N802
    name: str | None = None, **params: Any
) -> Definition:
    """Definition for the ``sr`` provider (default tolerance 0.5 ATR)."""
    return construct("sr", name, **params)


def DetectPullback(  # noqa: N802
    name: str | None = None, **params: Any
) -> Definition:
    """Definition for the ``detect_pullback`` provider."""
    return construct("detect_pullback", name, **params)


def GenerateSignal(  # noqa: N802
    name: str | None = None, **params: Any
) -> Definition:
    """Definition for the ``generate_signal`` provider (category ``signal``)."""
    return construct("generate_signal", name, **params)


def ManageRisk(  # noqa: N802
    name: str | None = None, **params: Any
) -> Definition:
    """Definition for the ``manage_risk`` provider (category ``risk``)."""
    return construct("manage_risk", name, **params)
