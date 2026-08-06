from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from marketatlas.analysis.ast.expressions import wrap
from marketatlas.analysis.ast.models import Parameter, Provider
from marketatlas.analysis.ast.param_schema import ParamSpec, derive_param_schema

logger = logging.getLogger(__name__)


class ProviderNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ProviderContract:
    """Fact-level contract of a provider (backlog 058).

    ``inputs`` are the fact key names the provider consumes and ``outputs``
    the fact key names it produces, both derived from the analyzer's runtime
    ``requires()``/``produces()`` at registration time (with default
    constructor arguments). Powers DSL shorthand disambiguation (backlog 057)
    and, later, binding validation against declared inputs/outputs.
    """

    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, list[Provider]] = {}
        self._param_schemas: dict[str, tuple[ParamSpec, ...]] = {}
        self._contracts: dict[str, ProviderContract] = {}

    def register_param_schema(self, key: str, schema: tuple[ParamSpec, ...]) -> None:
        """Attach a parameter schema to a provider name or capability key."""
        self._param_schemas[key] = schema

    def param_schema(self, key: str) -> tuple[ParamSpec, ...] | None:
        """Return the schema keyed by provider name/capability, or ``None``.

        ``None`` means no schema is registered for that key — callers skip
        param validation rather than false-positive (backlog 052).
        """
        return self._param_schemas.get(key)

    def register_contract(self, key: str, contract: ProviderContract) -> None:
        """Attach a fact-level contract to a provider name or capability key."""
        self._contracts[key] = contract

    def contract(self, key: str) -> ProviderContract | None:
        """Return the contract keyed by provider name/capability, or ``None``."""
        return self._contracts.get(key)

    def capabilities(self) -> tuple[str, ...]:
        """Sorted capability keys known to the registry."""
        return tuple(sorted(self._providers.keys()))

    def _register_metadata(self, provider: Provider, cls: type) -> None:
        schema = derive_param_schema(cls)
        if schema:
            self.register_param_schema(provider.name, schema)
            self.register_param_schema(provider.capability, schema)
        contract = _derive_contract(cls)
        self.register_contract(provider.name, contract)
        self.register_contract(provider.capability, contract)

    def register_provider(self, provider: Provider) -> None:
        cap = provider.capability
        if cap not in self._providers:
            self._providers[cap] = []
        self._providers[cap].append(provider)

    def register(
        self,
        capability_or_provider: str | type | Provider,
        cls: type | None = None,
        category: str = "analyzer",
        default_params: dict[str, Any] | None = None,
    ) -> Any:
        if isinstance(capability_or_provider, Provider):
            self.register_provider(capability_or_provider)
            return None

        if isinstance(capability_or_provider, type) and cls is None:
            capability = capability_or_provider.__name__
            params = tuple(
                Parameter(name=k, value=wrap(v)) for k, v in (default_params or {}).items()
            )
            provider = Provider(
                name=capability_or_provider.__name__,
                capability=capability,
                category=category,
                impl=capability_or_provider.__name__,
                default_params=params,
            )
            self.register_provider(provider)
            self._register_metadata(provider, capability_or_provider)
            return capability_or_provider

        if isinstance(capability_or_provider, str):
            if cls is not None:
                params = tuple(
                    Parameter(name=k, value=wrap(v)) for k, v in (default_params or {}).items()
                )
                provider = Provider(
                    name=cls.__name__,
                    capability=capability_or_provider,
                    category=category,
                    impl=cls.__name__,
                    default_params=params,
                )
                self.register_provider(provider)
                self._register_metadata(provider, cls)
                return None

            def decorator(target_cls: type) -> type:
                params = tuple(
                    Parameter(name=k, value=wrap(v)) for k, v in (default_params or {}).items()
                )
                provider = Provider(
                    name=target_cls.__name__,
                    capability=capability_or_provider,
                    category=category,
                    impl=target_cls.__name__,
                    default_params=params,
                )
                self.register_provider(provider)
                self._register_metadata(provider, target_cls)
                return target_cls

            return decorator

        raise TypeError(f"Unsupported argument type: {type(capability_or_provider)}")

    def resolve(self, capability: str, params: dict[str, Any] | None = None) -> Provider:
        providers = self._providers.get(capability, [])
        if not providers:
            available = ", ".join(sorted(self._providers.keys()))
            msg = f"No provider for capability '{capability}'. Available capabilities: {available}"
            raise ProviderNotFoundError(msg)
        if len(providers) > 1:
            logger.warning(
                "Multiple providers for capability '%s': %s. Picking first.",
                capability,
                [p.name for p in providers],
            )
        return providers[0]

    def list_providers(self) -> list[Provider]:
        result: list[Provider] = []
        for providers in self._providers.values():
            result.extend(providers)
        return result


def _derive_contract(cls: type) -> ProviderContract:
    """Derive a provider contract from an analyzer class at registration time.

    Instantiates the class with default constructor arguments and reads its
    ``requires()``/``produces()``, reducing each ``FactKey`` to its stable
    name. Classes without those methods (signals, risk engines, opaque
    providers) or that cannot be constructed with defaults yield an empty
    contract — the contract describes fact-level wiring only where the class
    exposes it (backlog 058).
    """
    requires = getattr(cls, "requires", None)
    produces = getattr(cls, "produces", None)
    if requires is None or produces is None:
        return ProviderContract()
    try:
        instance = cls()
    except Exception:
        return ProviderContract()
    inputs = tuple(str(fk.name) for fk in instance.requires())
    outputs = tuple(str(fk.name) for fk in instance.produces())
    return ProviderContract(inputs=inputs, outputs=outputs)


def _register_timeframe(registry: ProviderRegistry) -> None:
    """Register the ``timeframe`` value-producing capability (backlog 061).

    A ``TimeFrame`` definition is a compile-time value, never a runtime
    analyzer: its ``resolution`` param (a simple string literal like ``"1w"``)
    is resolved by the compiler and injected into ``AnalyzerConfig.timeframe``.
    Provider name doubles as the capability key so
    ``Definition.provider == "timeframe"`` stays the marker through registry
    resolution. No impl class and no fact contract — the definition produces
    nothing at runtime.
    """
    schema = (ParamSpec(name="resolution", required=True, expected_type=str),)
    registry.register_provider(
        Provider(name="timeframe", capability="timeframe", category="timeframe", impl="TimeFrame")
    )
    registry.register_param_schema("timeframe", schema)
    registry.register_contract("timeframe", ProviderContract())


def create_default_registry() -> ProviderRegistry:
    from marketatlas.analysis.analyzers.atr import ATRAnalyzer
    from marketatlas.analysis.analyzers.atr_series import ATRSeriesAnalyzer
    from marketatlas.analysis.analyzers.ema import EMAAnalyzer
    from marketatlas.analysis.analyzers.sr import SupportResistanceAnalyzer
    from marketatlas.analysis.analyzers.swing_basic import BasicSwingAnalyzer
    from marketatlas.analysis.analyzers.swing_structure import SwingStructureAnalyzer
    from marketatlas.analysis.analyzers.trend import TrendAnalyzer
    from marketatlas.analysis.patterns.four_swing_pullback import FourSwingPullbackDetector
    from marketatlas.analysis.signals.pullback_signal import PullbackSignal
    from marketatlas.strategy.risk import RiskEngine

    registry = ProviderRegistry()
    _register_timeframe(registry)
    registry.register("ema", EMAAnalyzer, default_params={"period": 20})
    registry.register("atr", ATRAnalyzer, default_params={"period": 14})
    registry.register("atr_series", ATRSeriesAnalyzer, default_params={"period": 14})
    registry.register("trend", TrendAnalyzer)
    registry.register("swingstructure", SwingStructureAnalyzer, default_params={"window": 50})
    registry.register("swings", BasicSwingAnalyzer, default_params={"lookback": 50})
    registry.register("sr", SupportResistanceAnalyzer)
    registry.register("detect_pullback", FourSwingPullbackDetector)
    registry.register("generate_signal", PullbackSignal, category="signal")
    registry.register("manage_risk", RiskEngine, category="risk")
    return registry
