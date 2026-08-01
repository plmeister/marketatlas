from __future__ import annotations

import logging
from typing import Any

from marketatlas.analysis.ast.expressions import wrap
from marketatlas.analysis.ast.models import Parameter, Provider
from marketatlas.analysis.ast.param_schema import ParamSpec, derive_param_schema

logger = logging.getLogger(__name__)


class ProviderNotFoundError(LookupError):
    pass


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, list[Provider]] = {}
        self._param_schemas: dict[str, tuple[ParamSpec, ...]] = {}

    def register_param_schema(self, key: str, schema: tuple[ParamSpec, ...]) -> None:
        """Attach a parameter schema to a provider name or capability key."""
        self._param_schemas[key] = schema

    def param_schema(self, key: str) -> tuple[ParamSpec, ...] | None:
        """Return the schema keyed by provider name/capability, or ``None``.

        ``None`` means no schema is registered for that key — callers skip
        param validation rather than false-positive (backlog 052).
        """
        return self._param_schemas.get(key)

    def _derive_and_register_schema(self, provider: Provider, cls: type) -> None:
        schema = derive_param_schema(cls)
        if schema:
            self.register_param_schema(provider.name, schema)
            self.register_param_schema(provider.capability, schema)

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
            self._derive_and_register_schema(provider, capability_or_provider)
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
                self._derive_and_register_schema(provider, cls)
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
                self._derive_and_register_schema(provider, target_cls)
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


def create_default_registry() -> ProviderRegistry:
    from marketatlas.analysis.analyzers.atr import ATRAnalyzer
    from marketatlas.analysis.analyzers.ema import EMAAnalyzer
    from marketatlas.analysis.analyzers.sr import SupportResistanceAnalyzer
    from marketatlas.analysis.analyzers.swing import SwingStructureAnalyzer
    from marketatlas.analysis.analyzers.swing_basic import BasicSwingAnalyzer
    from marketatlas.analysis.analyzers.trend import TrendAnalyzer
    from marketatlas.analysis.patterns.four_swing_pullback import FourSwingPullbackDetector
    from marketatlas.analysis.signals.pullback_signal import PullbackSignal
    from marketatlas.strategy.risk import RiskEngine

    registry = ProviderRegistry()
    registry.register("ema", EMAAnalyzer, default_params={"period": 20})
    registry.register("atr", ATRAnalyzer, default_params={"period": 14})
    registry.register("trend", TrendAnalyzer)
    registry.register("swingstructure", SwingStructureAnalyzer, default_params={"lookback": 50})
    registry.register("swings", BasicSwingAnalyzer, default_params={"lookback": 50})
    registry.register("sr", SupportResistanceAnalyzer)
    registry.register("detect_pullback", FourSwingPullbackDetector)
    registry.register("generate_signal", PullbackSignal, category="signal")
    registry.register("manage_risk", RiskEngine, category="risk")
    return registry
