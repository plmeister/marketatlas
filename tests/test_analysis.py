from datetime import UTC, datetime

import pytest
from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.graph import (
    AnalysisGraph,
    AnalyzerRegistry,
    CyclicDependencyError,
    UnsatisfiedDependencyError,
)
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
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
    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey("ema_20"),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        return AnalysisResult(
            facts=(
                EMAFact(
                    timestamp=view.current.timestamp,
                    evidence=(
                        EvidenceEntry(
                            text="EMA20 = 103.0",
                            level=EvidenceLevel.INFO,
                            source="ProduceXAnalyzer",
                        ),
                    ),
                    value=103.0,
                    period=20,
                ),
            ),
            evidence=(
                EvidenceEntry(
                    text="EMA20 = 103.0",
                    level=EvidenceLevel.INFO,
                    source="ProduceXAnalyzer",
                ),
            ),
        )


class RequireXProduceYAnalyzer(Analyzer):
    def requires(self) -> tuple[FactKey, ...]:
        return (FactKey("ema_20"),)

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey("trend"),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        _ema = facts[FactKey("ema_20")]
        return AnalysisResult(
            facts=(
                TrendFact(
                    timestamp=view.current.timestamp,
                    evidence=(
                        EvidenceEntry(
                            text="Trend: Bullish",
                            level=EvidenceLevel.INFO,
                            source="RequireXProduceYAnalyzer",
                        ),
                    ),
                    direction=TrendDirection.BULLISH,
                    strength=0.7,
                ),
            ),
            evidence=(
                EvidenceEntry(
                    text="Trend: Bullish",
                    level=EvidenceLevel.INFO,
                    source="RequireXProduceYAnalyzer",
                ),
            ),
        )


class RequireBothAnalyzer(Analyzer):
    def requires(self) -> tuple[FactKey, ...]:
        return (FactKey("ema_20"), FactKey("trend"))

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey("atr_14"),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        return AnalysisResult(
            facts=(
                ATRFact(
                    timestamp=view.current.timestamp,
                    evidence=(
                        EvidenceEntry(
                            text="ATR14 = 5.0",
                            level=EvidenceLevel.INFO,
                            source="RequireBothAnalyzer",
                        ),
                    ),
                    value=5.0,
                    period=14,
                ),
            ),
            evidence=(
                EvidenceEntry(
                    text="ATR14 = 5.0",
                    level=EvidenceLevel.INFO,
                    source="RequireBothAnalyzer",
                ),
            ),
        )


class TestAnalyzerBase:
    def test_requires_returns_tuple_of_fact_types(self) -> None:
        analyzer = ProduceXAnalyzer()
        assert analyzer.requires() == ()

    def test_produces_returns_tuple_of_fact_types(self) -> None:
        analyzer = ProduceXAnalyzer()
        assert analyzer.produces() == (FactKey("ema_20"),)

    def test_analyze_returns_analysis_result(self, view: MarketView) -> None:
        analyzer = ProduceXAnalyzer()
        result = analyzer.analyze(view, {})
        assert isinstance(result, AnalysisResult)
        assert len(result.facts) == 1
        assert isinstance(result.facts[0], EMAFact)

    def test_default_instance_key(self) -> None:
        """Analyzer base class default instance_key returns class name."""

        class MyAnalyzer(Analyzer):
            def requires(self) -> tuple[FactKey, ...]:
                return ()

            def produces(self) -> tuple[FactKey, ...]:
                return ()

            def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        analyzer = MyAnalyzer()
        assert analyzer.instance_key == "MyAnalyzer"


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
            def requires(self) -> tuple[FactKey, ...]:
                return (FactKey("trend"),)

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("ema_20"),)

            def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        class CyclicB(Analyzer):
            def requires(self) -> tuple[FactKey, ...]:
                return (FactKey("ema_20"),)

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("trend"),)

            def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        with pytest.raises(CyclicDependencyError):
            AnalysisGraph([CyclicA(), CyclicB()])

    def test_unsatisfied_dependency(self) -> None:
        class RequireMissing(Analyzer):
            def requires(self) -> tuple[FactKey, ...]:
                return (FactKey("atr_14"),)

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("trend"),)

            def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        with pytest.raises(UnsatisfiedDependencyError):
            AnalysisGraph([RequireMissing()])


class TestAnalysisGraphRun:
    def test_run_returns_all_produced_facts(self, view: MarketView) -> None:
        graph = AnalysisGraph([ProduceXAnalyzer(), RequireXProduceYAnalyzer()])
        facts = graph.run(view)
        assert FactKey("ema_20") in facts
        assert FactKey("trend") in facts

    def test_run_passes_facts_to_dependents(self, view: MarketView) -> None:
        graph = AnalysisGraph([ProduceXAnalyzer(), RequireXProduceYAnalyzer()])
        facts = graph.run(view)
        trend = facts[FactKey("trend")]
        assert isinstance(trend, TrendFact)
        assert trend.direction == TrendDirection.BULLISH

    def test_run_three_chain(self, view: MarketView) -> None:
        graph = AnalysisGraph(
            [
                ProduceXAnalyzer(),
                RequireXProduceYAnalyzer(),
                RequireBothAnalyzer(),
            ]
        )
        facts = graph.run(view)
        assert len(facts) == 3
        assert FactKey("atr_14") in facts

    def test_run_empty_graph(self, view: MarketView) -> None:
        graph = AnalysisGraph([])
        facts = graph.run(view)
        assert facts == {}

    def test_run_independent_analyzers(self, view: MarketView) -> None:
        class IndependentAnalyzer(Analyzer):
            def requires(self) -> tuple[FactKey, ...]:
                return ()

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("atr_14"),)

            def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
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
        ema = facts[FactKey("ema_20")]
        atr = facts[FactKey("atr_14")]
        assert isinstance(ema, EMAFact)
        assert isinstance(atr, ATRFact)
        assert ema.value == 103.0
        assert atr.value == 6.0


class TestAnalysisGraphDuplicateProducer:
    def test_duplicate_producer_raises(self) -> None:
        class DupA(Analyzer):
            def requires(self) -> tuple[FactKey, ...]:
                return ()

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("ema_20"),)

            def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        class DupB(Analyzer):
            def requires(self) -> tuple[FactKey, ...]:
                return ()

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("ema_20"),)

            def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        with pytest.raises(CyclicDependencyError):
            AnalysisGraph([DupA(), DupB()])


class TestAnalyzerRegistry:
    def test_register_and_build(self) -> None:
        registry = AnalyzerRegistry()
        registry.register(ProduceXAnalyzer)
        graph = registry.build()
        assert isinstance(graph, AnalysisGraph)
        order = graph.execution_order()
        assert len(order) == 1
        assert isinstance(order[0], ProduceXAnalyzer)

    def test_build_with_dependencies(self) -> None:
        registry = AnalyzerRegistry()
        registry.register(ProduceXAnalyzer)
        registry.register(RequireXProduceYAnalyzer)
        graph = registry.build()
        order = graph.execution_order()
        assert len(order) == 2
        assert isinstance(order[0], ProduceXAnalyzer)
        assert isinstance(order[1], RequireXProduceYAnalyzer)

    def test_build_with_kwargs(self) -> None:
        class KwargsAnalyzer(Analyzer):
            def __init__(self, period: int = 20) -> None:
                self._period = period

            def requires(self) -> tuple[FactKey, ...]:
                return ()

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey(f"ema_{self._period}"),)

            def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        registry = AnalyzerRegistry()
        registry.register(KwargsAnalyzer, period=50)
        graph = registry.build()
        order = graph.execution_order()
        assert len(order) == 1
        assert order[0].produces() == (FactKey("ema_50"),)

    def test_resolve_selects_needed(self) -> None:
        registry = AnalyzerRegistry()
        registry.register(ProduceXAnalyzer)
        registry.register(RequireXProduceYAnalyzer)
        registry.register(RequireBothAnalyzer)
        graph = registry.resolve({FactKey("trend")})
        order = graph.execution_order()
        names = [type(a).__name__ for a in order]
        assert "ProduceXAnalyzer" in names
        assert "RequireXProduceYAnalyzer" in names
        assert "RequireBothAnalyzer" not in names

    def test_resolve_all_needed(self) -> None:
        registry = AnalyzerRegistry()
        registry.register(ProduceXAnalyzer)
        registry.register(RequireXProduceYAnalyzer)
        registry.register(RequireBothAnalyzer)
        graph = registry.resolve({FactKey("atr_14")})
        order = graph.execution_order()
        assert len(order) == 3

    def test_resolve_unsatisfied_raises(self) -> None:
        registry = AnalyzerRegistry()
        registry.register(RequireXProduceYAnalyzer)
        with pytest.raises(UnsatisfiedDependencyError):
            registry.resolve({FactKey("trend")})

    def test_resolve_empty_needed(self) -> None:
        registry = AnalyzerRegistry()
        registry.register(ProduceXAnalyzer)
        graph = registry.resolve(set())
        assert len(graph.execution_order()) == 0


class TestFactKeyTimeframe:
    def test_default_timeframe_none(self) -> None:
        fk = FactKey("ema_20")
        assert fk.timeframe is None

    def test_with_timeframe(self) -> None:
        fk = FactKey("swing", timeframe=Timeframe.W1)
        assert fk.timeframe == Timeframe.W1

    def test_str_with_timeframe(self) -> None:
        fk = FactKey("swing", timeframe=Timeframe.W1)
        assert "tf_1w" in str(fk)

    def test_str_with_params_and_timeframe(self) -> None:
        fk = FactKey.from_params("ema", period=20, timeframe=Timeframe.D1)
        assert "ema" in str(fk)
        assert "period_20" in str(fk)
        assert "tf_1d" in str(fk)

    def test_equality_respects_timeframe(self) -> None:
        fk1 = FactKey("swing", timeframe=Timeframe.W1)
        fk2 = FactKey("swing", timeframe=Timeframe.D1)
        assert fk1 != fk2

    def test_from_params_accepts_timeframe(self) -> None:
        fk = FactKey.from_params("atr", period=14, timeframe=Timeframe.D1)
        assert fk.timeframe == Timeframe.D1


class TestFactVisibleOn:
    def test_default_visible_on_none(self) -> None:
        fact = Fact(timestamp=BASE, evidence=())
        assert fact.visible_on is None

    def test_visible_on_restricts_resolution(self) -> None:
        fact = Fact(
            timestamp=BASE,
            evidence=(),
            visible_on=frozenset({Timeframe.W1}),
        )
        assert fact.visible_on is not None
        assert Timeframe.W1 in fact.visible_on
        assert Timeframe.D1 not in fact.visible_on

    def test_visible_on_all_resolutions(self) -> None:
        fact = Fact(timestamp=BASE, evidence=(), visible_on=None)
        assert fact.visible_on is None


class TestAnalyzerTimeframe:
    def test_default_timeframe_none(self) -> None:
        analyzer = ProduceXAnalyzer()
        assert analyzer.timeframe is None

    def test_concrete_timeframe(self) -> None:
        class WeeklyAnalyzer(Analyzer):
            @property
            def timeframe(self) -> Timeframe:
                return Timeframe.W1

            def requires(self) -> tuple[FactKey, ...]:
                return ()

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("weekly_indicator"),)

            def analyze(
                self, view: MarketView, facts: dict[FactKey, Fact]
            ) -> AnalysisResult:
                return AnalysisResult(facts=(), evidence=())

        analyzer = WeeklyAnalyzer()
        assert analyzer.timeframe == Timeframe.W1


class TestCrossResolutionGraph:
    @pytest.fixture()
    def multi_tf_store(self) -> MarketStore:
        from datetime import timedelta

        base = datetime(2024, 1, 1, tzinfo=UTC)
        daily = tuple(
            Candle(
                timestamp=base + timedelta(days=i),
                open=100.0 + i, high=105.0 + i,
                low=99.0 + i, close=103.0 + i, volume=1000.0,
            )
            for i in range(100)
        )
        weekly = tuple(
            Candle(
                timestamp=base + timedelta(weeks=i),
                open=100.0 + i * 5, high=110.0 + i * 5,
                low=95.0 + i * 5, close=105.0 + i * 5, volume=5000.0,
            )
            for i in range(15)
        )
        dd = MarketData(symbol=Symbol("TEST"), timeframe=Timeframe.D1, candles=daily)
        ww = MarketData(symbol=Symbol("TEST"), timeframe=Timeframe.W1, candles=weekly)
        return MarketStore({Timeframe.D1: dd, Timeframe.W1: ww})

    def test_weekly_analyzer_gets_correct_data(
        self, multi_tf_store: MarketStore
    ) -> None:
        class WeeklyHighAnalyzer(Analyzer):
            @property
            def timeframe(self) -> Timeframe:
                return Timeframe.W1

            def requires(self) -> tuple[FactKey, ...]:
                return ()

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("weekly_high", timeframe=Timeframe.W1),)

            def analyze(
                self, view: MarketView, facts: dict[FactKey, Fact]
            ) -> AnalysisResult:
                weekly_high = max(view.highs[-5:]) if view.highs else 0.0
                return AnalysisResult(
                    facts=(
                        Fact(
                            timestamp=view.current.timestamp,
                            evidence=(),
                            visible_on=frozenset({Timeframe.W1}),
                        ),
                    ),
                    evidence=(),
                )

        view = MarketView(multi_tf_store, cursor=99, window_size=50)
        graph = AnalysisGraph([WeeklyHighAnalyzer()])
        facts = graph.run(view)
        weekly_key = FactKey("weekly_high", timeframe=Timeframe.W1)
        assert weekly_key in facts
        assert facts[weekly_key].visible_on == frozenset({Timeframe.W1})

    def test_mixed_resolution_graph(
        self, multi_tf_store: MarketStore
    ) -> None:
        class DailyEMAAnalyzer(Analyzer):
            def requires(self) -> tuple[FactKey, ...]:
                return ()

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("ema_20"),)

            def analyze(
                self, view: MarketView, facts: dict[FactKey, Fact]
            ) -> AnalysisResult:
                return AnalysisResult(
                    facts=(
                        EMAFact(
                            timestamp=view.current.timestamp,
                            evidence=(),
                            value=100.0, period=20,
                        ),
                    ),
                    evidence=(),
                )

        class WeeklyConsumer(Analyzer):
            @property
            def timeframe(self) -> Timeframe:
                return Timeframe.W1

            def requires(self) -> tuple[FactKey, ...]:
                return (FactKey("ema_20"),)

            def produces(self) -> tuple[FactKey, ...]:
                return (FactKey("weekly_signal", timeframe=Timeframe.W1),)

            def analyze(
                self, view: MarketView, facts: dict[FactKey, Fact]
            ) -> AnalysisResult:
                ema = facts[FactKey("ema_20")]
                assert isinstance(ema, EMAFact)
                return AnalysisResult(
                    facts=(
                        Fact(
                            timestamp=view.current.timestamp,
                            evidence=(),
                            visible_on=frozenset({Timeframe.W1}),
                        ),
                    ),
                    evidence=(),
                )

        view = MarketView(multi_tf_store, cursor=99, window_size=50)
        graph = AnalysisGraph([DailyEMAAnalyzer(), WeeklyConsumer()])
        facts = graph.run(view)
        assert FactKey("ema_20") in facts
        assert FactKey("weekly_signal", timeframe=Timeframe.W1) in facts
