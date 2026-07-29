from __future__ import annotations

from marketatlas.analysis.ast.models import Analysis, Provider
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.strategy.config import (
    AnalyzerConfig,
    RiskConfig,
    SignalConfig,
    StrategyConfig,
)
from marketatlas.strategy.loader import build_analyzers


def _provider_map(analysis: Analysis) -> dict[str, Provider]:
    return {p.name: p for p in analysis.providers}


class ASTCompiler:
    @staticmethod
    def to_config(analysis: Analysis) -> StrategyConfig:
        providers = _provider_map(analysis)
        analyzer_configs: list[AnalyzerConfig] = []
        signal_configs: list[SignalConfig] = []
        risk_config: RiskConfig = RiskConfig(algorithm="none")

        for d in analysis.definitions:
            provider = providers.get(d.provider)
            if provider is None:
                raise ValueError(f"Unknown provider: {d.provider}")

            params = {p.name: p.value for p in d.parameters}

            if provider.category == "analyzer":
                analyzer_configs.append(
                    AnalyzerConfig(type=provider.impl, params=params)
                )
            elif provider.category == "signal":
                requires = tuple(b.output for b in d.bindings)
                signal_configs.append(
                    SignalConfig(type=provider.impl, requires=requires, rules=params)
                )
            elif provider.category == "risk":
                risk_config = RiskConfig(algorithm=provider.impl, params=params)

        return StrategyConfig(
            name=analysis.name,
            version=analysis.version,
            analyzers=tuple(analyzer_configs),
            signals=tuple(signal_configs),
            risk=risk_config,
        )

    @staticmethod
    def compile(analysis: Analysis) -> AnalysisGraph:
        config = ASTCompiler.to_config(analysis)
        analyzers = build_analyzers(config)
        return AnalysisGraph(analyzers)
