from datetime import UTC, datetime

import pytest

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.graph import (
    AnalysisGraph,
    CyclicDependencyError,
    UnsatisfiedDependencyError,
)
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import TrendDirection, TrendFact

BASE = datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture()
def store() -> MarketStore:
    candles = tuple(
        Candle(
            timestamp=BASE,
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=1000.0,
        )
        for _ in range(100)
    )
    data = MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
    return MarketStore(data)


@pytest.fixture()
def view(store: MarketStore) -> MarketView:
    return MarketView(store, cursor=99, window_size=50)


class ProduceXAnalyzer(Analyzer):
    def requires(self) -> tuple[type[Fact], ...]:
        return ()

    def produces(self) -> tuple[type[Fact], ...]:
        return (EMAFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult:
        return AnalysisResult(
            facts=(
                EMAFact(
                    timestamp=view.current.timestamp,
                    evidence=("EMA20 = 103.0",),
                    value=103.0,
                    period=20,
                ),
            ),
            evidence=("EMA20 = 103.0",),
        )


class RequireXProduceYAnalyzer(Analyzer):
    def requires(self) -> tuple[type[Fact], ...]:
        return (EMAFact,)

    def produces(self) -> tuple[type[Fact], ...]:
        return (TrendFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult:
        _ema = facts[EMAFact]
        return AnalysisResult(
            facts=(
                TrendFact(
                    timestamp=view.current.timestamp,
                    evidence=("Trend: Bullish",),
                    direction=TrendDirection.BULLISH,
                    strength=0.7,
                ),
            ),
            evidence=("Trend: Bullish",),
        )


class RequireBothAnalyzer(Analyzer):
    def requires(self) -> tuple[type[Fact], ...]:
        return (EMAFact, TrendFact)

    def produces(self) -> tuple[type[Fact], ...]:
        return (ATRFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult:
        return AnalysisResult(
            facts=(
                ATRFact(
                    timestamp=view.current.timestamp,
                    evidence=("ATR14 = 5.0",),
                    value=5.0,
                    period=14,
                ),
            ),
            evidence=("ATR14 = 5.0",),
        )


class TestAnalyzerBase:
    def test_requires_returns_tuple_of_fact_types(self) -> None:
        analyzer = ProduceXAnalyzer()
        assert analyzer.requires() == ()

    def test_produces_returns_tuple_of_fact_types(self) -> None:
        analyzer = ProduceXAnalyzer()
        assert analyzer.produces() == (EMAFact,)

    def test_analyze_returns_analysis_result(self, view: MarketView) -> None:
        analyzer = ProduceXAnalyzer()
        result = analyzer.analyze(view, {})
        assert isinstance(result, AnalysisResult)
        assert len(result.facts) == 1
        assert isinstance(result.facts[0], EMAFact)


class TestAnalysisResult:
    def test_frozen(self) -> None:
        result = AnalysisResult(facts=(), evidence=())
        with pytest.raises(AttributeError):
            result.facts = ()  # type: ignore[misc]

    def test_diagnostics_default_empty(self) -> None:
        result = AnalysisResult(facts=(), evidence=())
        assert result.diagnostics == ()


class TestAnalysisGraphExecutionOrder:
    def test_single_analyzer(self) -> None:
        graph = AnalysisGraph([ProduceXAnalyzer()])
        order = graph.execution_order()
        assert len(order) == 1
        assert isinstance(order[0], ProduceXAnalyzer)

    def test_dependency_order(self) -> None:
        a = RequireXProduceYAnalyzer()
        b = ProduceXAnalyzer()
        graph = AnalysisGraph([a, b])
        order = graph.execution_order()
        assert isinstance(order[0], ProduceXAnalyzer)
        assert isinstance(order[1], RequireXProduceYAnalyzer)

    def test_three_analyzer_chain(self) -> None:
        a = RequireBothAnalyzer()
        b = RequireXProduceYAnalyzer()
        c = ProduceXAnalyzer()
        graph = AnalysisGraph([a, b, c])
        order = graph.execution_order()
        assert isinstance(order[0], ProduceXAnalyzer)
        assert isinstance(order[1], RequireXProduceYAnalyzer)
        assert isinstance(order[2], RequireBothAnalyzer)

    def test_preserves_analyzer_instances(self) -> None:
        a = ProduceXAnalyzer()
        b = RequireXProduceYAnalyzer()
        graph = AnalysisGraph([a, b])
        order = graph.execution_order()
        assert order[0] is a
        assert order[1] is b


class TestAnalysisGraphErrors:
    def test_cyclic_dependency(self) -> None:
        class CyclicA(Analyzer):
            def requires(self) -> tuple[type[Fact], ...]:
                return (TrendFact,)

            def produces(self) -> tuple[type[Fact], ...]:
                return (EMAFact,)

            def analyze(
                self, view: MarketView, facts: dict[type[Fact], Fact]
            ) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        class CyclicB(Analyzer):
            def requires(self) -> tuple[type[Fact], ...]:
                return (EMAFact,)

            def produces(self) -> tuple[type[Fact], ...]:
                return (TrendFact,)

            def analyze(
                self, view: MarketView, facts: dict[type[Fact], Fact]
            ) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        with pytest.raises(CyclicDependencyError):
            AnalysisGraph([CyclicA(), CyclicB()])

    def test_unsatisfied_dependency(self) -> None:
        class RequireMissing(Analyzer):
            def requires(self) -> tuple[type[Fact], ...]:
                return (ATRFact,)

            def produces(self) -> tuple[type[Fact], ...]:
                return (TrendFact,)

            def analyze(
                self, view: MarketView, facts: dict[type[Fact], Fact]
            ) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        with pytest.raises(UnsatisfiedDependencyError):
            AnalysisGraph([RequireMissing()])


class TestAnalysisGraphRun:
    def test_run_returns_all_produced_facts(self, view: MarketView) -> None:
        graph = AnalysisGraph([ProduceXAnalyzer(), RequireXProduceYAnalyzer()])
        facts = graph.run(view)
        assert EMAFact in facts
        assert TrendFact in facts

    def test_run_passes_facts_to_dependents(self, view: MarketView) -> None:
        graph = AnalysisGraph([ProduceXAnalyzer(), RequireXProduceYAnalyzer()])
        facts = graph.run(view)
        trend = facts[TrendFact]
        assert isinstance(trend, TrendFact)
        assert trend.direction == TrendDirection.BULLISH

    def test_run_three_chain(self, view: MarketView) -> None:
        graph = AnalysisGraph([
            ProduceXAnalyzer(),
            RequireXProduceYAnalyzer(),
            RequireBothAnalyzer(),
        ])
        facts = graph.run(view)
        assert len(facts) == 3
        assert ATRFact in facts

    def test_run_empty_graph(self, view: MarketView) -> None:
        graph = AnalysisGraph([])
        facts = graph.run(view)
        assert facts == {}

    def test_run_independent_analyzers(self, view: MarketView) -> None:
        class IndependentAnalyzer(Analyzer):
            def requires(self) -> tuple[type[Fact], ...]:
                return ()

            def produces(self) -> tuple[type[Fact], ...]:
                return (ATRFact,)

            def analyze(
                self, view: MarketView, facts: dict[type[Fact], Fact]
            ) -> AnalysisResult:
                return AnalysisResult(
                    facts=(
                        ATRFact(
                            timestamp=view.current.timestamp,
                            evidence=(),
                            value=6.0,
                            period=14,
                        ),
                    ),
                    evidence=(),
                )

        graph = AnalysisGraph([ProduceXAnalyzer(), IndependentAnalyzer()])
        facts = graph.run(view)
        assert len(facts) == 2
        ema = facts[EMAFact]
        atr = facts[ATRFact]
        assert isinstance(ema, EMAFact)
        assert isinstance(atr, ATRFact)
        assert ema.value == 103.0
        assert atr.value == 6.0
