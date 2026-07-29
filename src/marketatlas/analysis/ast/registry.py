from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from marketatlas.analysis.ast.models import Parameter, Provider

logger = logging.getLogger(__name__)


class ProviderNotFoundError(LookupError):
    pass


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, list[Provider]] = {}

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
                Parameter(name=k, value=v) for k, v in (default_params or {}).items()
            )
            provider = Provider(
                name=capability_or_provider.__name__,
                capability=capability,
                category=category,
                impl=capability_or_provider.__name__,
                default_params=params,
            )
            self.register_provider(provider)
            return capability_or_provider

        if isinstance(capability_or_provider, str):
            if cls is not None:
                params = tuple(
                    Parameter(name=k, value=v) for k, v in (default_params or {}).items()
                )
                provider = Provider(
                    name=cls.__name__,
                    capability=capability_or_provider,
                    category=category,
                    impl=cls.__name__,
                    default_params=params,
                )
                self.register_provider(provider)
                return None

            def decorator(target_cls: type) -> type:
                params = tuple(
                    Parameter(name=k, value=v) for k, v in (default_params or {}).items()
                )
                provider = Provider(
                    name=target_cls.__name__,
                    capability=capability_or_provider,
                    category=category,
                    impl=target_cls.__name__,
                    default_params=params,
                )
                self.register_provider(provider)
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
    from marketatlas.analysis.analyzers.trend import TrendAnalyzer
    from marketatlas.analysis.patterns.four_swing_pullback import FourSwingPullbackDetector
    from marketatlas.analysis.signals.pullback_signal import PullbackSignal
    from marketatlas.strategy.risk import RiskEngine

    registry = ProviderRegistry()
    registry.register("compute_ema", EMAAnalyzer, default_params={"period": 20})
    registry.register("compute_atr", ATRAnalyzer, default_params={"period": 14})
    registry.register("analyze_trend", TrendAnalyzer)
    registry.register("detect_swings", SwingStructureAnalyzer, default_params={"lookback": 50})
    registry.register("find_support_resistance", SupportResistanceAnalyzer)
    registry.register("detect_pullback", FourSwingPullbackDetector)
    registry.register("generate_signal", PullbackSignal, category="signal")
    registry.register("manage_risk", RiskEngine, category="risk")
    return registry
