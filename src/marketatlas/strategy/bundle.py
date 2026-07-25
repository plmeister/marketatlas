from __future__ import annotations

from marketatlas.analysis.graph import AnalysisGraph, FactKey
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact
from marketatlas.strategy.risk import RiskEngine
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.strategy import Strategy
from marketatlas.strategy.tradebook import TradeBook


class StrategyBundle:
    """Combines multiple strategies into a single analysis graph."""

    def __init__(
        self,
        strategies: list[Strategy],
        initial_balance: float = 1000.0,
    ) -> None:
        self._strategies = {s.name: s for s in strategies}
        self._graph = self._merge_graphs(strategies)
        self._tradebook = TradeBook(initial_balance)

    @property
    def tradebook(self) -> TradeBook:
        return self._tradebook

    @property
    def graph(self) -> AnalysisGraph:
        return self._graph

    @property
    def strategies(self) -> dict[str, Strategy]:
        return dict(self._strategies)

    def evaluate_all(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> list[tuple[str, TradeSignal]]:
        results: list[tuple[str, TradeSignal]] = []
        for name, strategy in self._strategies.items():
            for signal in strategy.evaluate(view, facts):
                results.append((name, signal))
        return results

    def get_risk_engine(self, strategy_name: str) -> RiskEngine:
        strategy = self._strategies[strategy_name]
        return strategy.risk_engine

    def _merge_graphs(self, strategies: list[Strategy]) -> AnalysisGraph:
        from marketatlas.analysis.base import Analyzer

        seen: dict[int, Analyzer] = {}
        seen_keys: dict[object, int] = {}
        for strategy in strategies:
            for analyzer in strategy.graph.execution_order():
                key: object = (
                    type(analyzer),
                    tuple(sorted(analyzer.requires(), key=lambda r: (r[0].__name__, r[1]))),
                    frozenset(sorted(analyzer.produces(), key=lambda p: (p[0].__name__, p[1]))),
                )
                if key not in seen_keys:
                    seen_keys[key] = id(analyzer)
                    seen[id(analyzer)] = analyzer
        merged: list[Analyzer] = [seen[k] for k in seen_keys.values()]
        return AnalysisGraph(merged)
