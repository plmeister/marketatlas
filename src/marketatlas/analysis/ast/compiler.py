from __future__ import annotations

from marketatlas.analysis.ast.models import Analysis
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.strategy.config import (
    AnalyzerConfig,
    RiskConfig,
    SignalConfig,
    StrategyConfig,
)
from marketatlas.strategy.loader import build_analyzers


class ASTCompiler:
    @staticmethod
    def to_config(analysis: Analysis) -> StrategyConfig:
        analyzer_configs: list[AnalyzerConfig] = []
        signal_configs: list[SignalConfig] = []
        risk_config: RiskConfig = RiskConfig(algorithm="none")

        for d in analysis.definitions:
            params = {p.name: p.value for p in d.parameters}

            if d.type == "analyzer":
                analyzer_configs.append(
                    AnalyzerConfig(type=d.impl, params=params)
                )
            elif d.type == "signal":
                requires = tuple(b.output for b in d.bindings)
                signal_configs.append(
                    SignalConfig(type=d.impl, requires=requires, rules=params)
                )
            elif d.type == "risk":
                risk_config = RiskConfig(algorithm=d.impl, params=params)

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
