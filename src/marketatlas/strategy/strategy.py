from __future__ import annotations

from marketatlas.analysis.graph import AnalysisGraph, FactKey
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact
from marketatlas.strategy.config import StrategyConfig
from marketatlas.strategy.loader import build_analyzers
from marketatlas.strategy.risk import RiskEngine
from marketatlas.strategy.signals import Signal, TradeSignal


class Strategy:
    def __init__(self, name: str, config: StrategyConfig) -> None:
        self._name = name
        self._config = config
        self._graph = self._build_graph()
        self._signals = self._build_signals()
        self._risk_engine = self._build_risk()

    @property
    def config(self) -> StrategyConfig:
        return self._config

    @property
    def name(self) -> str:
        return self._name

    @property
    def graph(self) -> AnalysisGraph:
        return self._graph

    @property
    def risk_engine(self) -> RiskEngine:
        return self._risk_engine

    def evaluate(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> list[TradeSignal]:
        results: list[TradeSignal] = []
        for signal in self._signals:
            ts = signal.evaluate(view, facts)
            if ts is not None and ts.confidence > 0:
                results.append(ts)
        return results

    def evaluate_with_rejections(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> tuple[list[TradeSignal], list[TradeSignal]]:
        signals: list[TradeSignal] = []
        rejections: list[TradeSignal] = []
        for signal in self._signals:
            ts = signal.evaluate(view, facts)
            if ts is not None and ts.confidence > 0:
                signals.append(ts)
            elif ts is not None and ts.rejections:
                rejections.append(ts)
        return signals, rejections

    def _build_graph(self) -> AnalysisGraph:
        analyzers = build_analyzers(self._config)
        return AnalysisGraph(analyzers)

    def _build_signals(self) -> list[Signal]:
        from marketatlas.analysis.signals.pullback_signal import PullbackSignal

        signal_types: dict[str, type[Signal]] = {
            "PullbackSignal": PullbackSignal,
        }
        signals: list[Signal] = []
        for sc in self._config.signals:
            cls = signal_types.get(sc.type)
            if cls is None:
                raise ValueError(f"Unknown signal type '{sc.type}'")
            signals.append(cls(**sc.rules))
        return signals

    def _build_risk(self) -> RiskEngine:
        rc = self._config.risk
        return RiskEngine(**rc.params)
