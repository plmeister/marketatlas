from datetime import UTC, datetime

from marketatlas.analysis.factkey import FactKey
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact
from marketatlas.strategy.bundle import StrategyBundle
from marketatlas.strategy.config import AnalyzerConfig, SignalConfig, StrategyConfig
from marketatlas.strategy.strategy import Strategy

BASE = datetime(2024, 1, 1, tzinfo=UTC)

CandleTuple = tuple[float, float, float, float, float]


def _make_store(candles_data: list[CandleTuple]) -> MarketStore:
    candles = tuple(
        Candle(timestamp=BASE, open=o, high=h, low=lo, close=c, volume=v)
        for o, h, lo, c, v in candles_data
    )
    return MarketStore(
        MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
    )


def _flat_candles(n: int = 50) -> list[CandleTuple]:
    return [(100.0, 101.0, 99.0, 100.0, 1000.0)] * n


def _strategy_config(
    name: str = "test",
    analyzers: tuple[AnalyzerConfig, ...] = (),
    signals: tuple[SignalConfig, ...] = (),
) -> StrategyConfig:
    return StrategyConfig(name=name, version="1.0", analyzers=analyzers, signals=signals)


class TestStrategyBundleInit:
    def test_single_strategy(self) -> None:
        config = _strategy_config()
        s = Strategy("s1", config)
        bundle = StrategyBundle([s])
        assert bundle.strategies == {"s1": s}
        assert bundle.graph is not None
        assert bundle.tradebook.balance == 1000.0

    def test_strategy_config_property(self) -> None:
        config = _strategy_config(name="mystrat")
        s = Strategy("s1", config)
        assert s.config is config
        assert s.config.name == "mystrat"

    def test_custom_balance(self) -> None:
        config = _strategy_config()
        s = Strategy("s1", config)
        bundle = StrategyBundle([s], initial_balance=5000.0)
        assert bundle.tradebook.balance == 5000.0

    def test_empty_strategies(self) -> None:
        bundle = StrategyBundle([])
        assert bundle.strategies == {}
        assert len(bundle.graph.execution_order()) == 0
        assert bundle.tradebook.balance == 1000.0


class TestMergeGraphs:
    def test_single_strategy_graph_preserved(self) -> None:
        config = _strategy_config(
            analyzers=(AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),)
        )
        s = Strategy("s1", config)
        bundle = StrategyBundle([s])
        order = bundle.graph.execution_order()
        assert len(order) == 1

    def test_duplicate_analyzers_deduplicated(self) -> None:
        config1 = _strategy_config(
            name="s1",
            analyzers=(AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),),
        )
        config2 = _strategy_config(
            name="s2",
            analyzers=(AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),),
        )
        s1 = Strategy("s1", config1)
        s2 = Strategy("s2", config2)
        bundle = StrategyBundle([s1, s2])
        order = bundle.graph.execution_order()
        assert len(order) == 1

    def test_different_analyzers_both_present(self) -> None:
        config1 = _strategy_config(
            name="s1",
            analyzers=(AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),),
        )
        config2 = _strategy_config(
            name="s2",
            analyzers=(AnalyzerConfig(type="ATRAnalyzer", params={"period": 14}),),
        )
        s1 = Strategy("s1", config1)
        s2 = Strategy("s2", config2)
        bundle = StrategyBundle([s1, s2])
        order = bundle.graph.execution_order()
        assert len(order) == 2


class TestEvaluateAll:
    def test_no_signals_returns_empty(self) -> None:
        config = _strategy_config()
        s = Strategy("s1", config)
        bundle = StrategyBundle([s])
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        results = bundle.evaluate_all(view, {})
        assert results == []

    def test_with_signals(self) -> None:
        config = _strategy_config(
            signals=(SignalConfig(type="PullbackSignal", rules={"min_strength": 0.5}),)
        )
        s = Strategy("s1", config)
        bundle = StrategyBundle([s])

        from marketatlas.facts.pattern import PullbackFact
        from marketatlas.facts.primitive import ATRFact
        from marketatlas.facts.structural import TrendDirection, TrendFact

        facts: dict[FactKey, Fact] = {
            FactKey("pullback_pattern"): PullbackFact(
                timestamp=BASE,
                evidence=(),
                direction=TrendDirection.BULLISH,
                swing_pattern=(48200.0, 51500.0, 49100.0, 52800.0),
            ),
            FactKey("trend"): TrendFact(
                timestamp=BASE,
                evidence=(),
                direction=TrendDirection.BULLISH,
                strength=0.7,
            ),
            FactKey("atr_14"): ATRFact(
                timestamp=BASE,
                evidence=(),
                value=50.0,
                period=14,
            ),
        }

        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        results = bundle.evaluate_all(view, facts)
        assert len(results) == 1
        name, signal = results[0]
        assert name == "s1"
        assert signal.direction == TrendDirection.BULLISH

    def test_multiple_strategies_combine_signals(self) -> None:
        from marketatlas.facts.pattern import PullbackFact
        from marketatlas.facts.primitive import ATRFact
        from marketatlas.facts.structural import TrendDirection, TrendFact

        config1 = _strategy_config(
            name="s1",
            signals=(SignalConfig(type="PullbackSignal", rules={"min_strength": 0.5}),),
        )
        config2 = _strategy_config(
            name="s2",
            signals=(SignalConfig(type="PullbackSignal", rules={"min_strength": 0.3}),),
        )
        s1 = Strategy("s1", config1)
        s2 = Strategy("s2", config2)
        bundle = StrategyBundle([s1, s2])

        facts: dict[FactKey, Fact] = {
            FactKey("pullback_pattern"): PullbackFact(
                timestamp=BASE,
                evidence=(),
                direction=TrendDirection.BULLISH,
                swing_pattern=(100.0, 200.0, 160.0, 260.0),
            ),
            FactKey("trend"): TrendFact(
                timestamp=BASE,
                evidence=(),
                direction=TrendDirection.BULLISH,
                strength=0.7,
            ),
            FactKey("atr_14"): ATRFact(
                timestamp=BASE,
                evidence=(),
                value=50.0,
                period=14,
            ),
        }

        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        results = bundle.evaluate_all(view, facts)
        names = [name for name, _ in results]
        assert "s1" not in names
        assert "s2" in names


class TestGetRiskEngine:
    def test_returns_correct_risk_engine(self) -> None:
        config = _strategy_config()
        s = Strategy("s1", config)
        bundle = StrategyBundle([s])
        engine = bundle.get_risk_engine("s1")
        assert engine is s.risk_engine

    def test_unknown_strategy_raises(self) -> None:
        config = _strategy_config()
        s = Strategy("s1", config)
        bundle = StrategyBundle([s])
        try:
            bundle.get_risk_engine("nonexistent")
            assert False, "Should raise KeyError"
        except KeyError:
            pass


class TestStrategiesProperty:
    def test_returns_copy(self) -> None:
        config = _strategy_config()
        s = Strategy("s1", config)
        bundle = StrategyBundle([s])
        strats = bundle.strategies
        strats["extra"] = Strategy("extra", _strategy_config())
        assert "extra" not in bundle.strategies
