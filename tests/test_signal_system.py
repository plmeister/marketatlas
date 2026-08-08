from datetime import UTC, datetime
from pathlib import Path

from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.signals.pullback_signal import PullbackSignal
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.pattern import PullbackFact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import TrendDirection, TrendFact
from marketatlas.strategy.config import AnalyzerConfig, SignalConfig, StrategyConfig
from marketatlas.strategy.loader import load_strategy, validate_config
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.strategy import Strategy

BASE = datetime(2024, 1, 1, tzinfo=UTC)

CandleTuple = tuple[float, float, float, float, float]


def _make_store(candles_data: list[CandleTuple]) -> MarketStore:
    candles = tuple(
        Candle(
            timestamp=BASE,
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=v,
        )
        for o, h, lo, c, v in candles_data
    )
    data = MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
    return MarketStore(data)


def _flat_candles(n: int = 50) -> list[CandleTuple]:
    return [(100.0, 101.0, 99.0, 100.0, 1000.0)] * n


def _bullish_pullback_fact() -> PullbackFact:
    return PullbackFact(
        timestamp=BASE,
        evidence=(
            EvidenceEntry(
                text="4-swing bullish pattern detected",
                level=EvidenceLevel.SIGNAL,
                source="PullbackPatternAnalyzer",
            ),
        ),
        direction=TrendDirection.BULLISH,
        swing_pattern=(48200.0, 51500.0, 49100.0, 52800.0),
    )


def _bearish_pullback_fact() -> PullbackFact:
    return PullbackFact(
        timestamp=BASE,
        evidence=(
            EvidenceEntry(
                text="4-swing bearish pattern detected",
                level=EvidenceLevel.SIGNAL,
                source="PullbackPatternAnalyzer",
            ),
        ),
        direction=TrendDirection.BEARISH,
        swing_pattern=(52000.0, 49000.0, 51000.0, 48000.0),
    )


def _weak_pullback_fact() -> PullbackFact:
    return PullbackFact(
        timestamp=BASE,
        evidence=(),
        direction=TrendDirection.BULLISH,
        swing_pattern=(),
    )


def _neutral_pullback_fact() -> PullbackFact:
    return PullbackFact(
        timestamp=BASE,
        evidence=(),
        direction=TrendDirection.NEUTRAL,
        swing_pattern=(),
    )


def _bullish_trend_fact(strength: float = 0.7) -> TrendFact:
    return TrendFact(
        timestamp=BASE,
        evidence=(
            EvidenceEntry(
                text="Trend: Bullish",
                level=EvidenceLevel.INFO,
                source="TrendAnalyzer",
            ),
        ),
        direction=TrendDirection.BULLISH,
        strength=strength,
    )


def _bearish_trend_fact(strength: float = 0.7) -> TrendFact:
    return TrendFact(
        timestamp=BASE,
        evidence=(),
        direction=TrendDirection.BEARISH,
        strength=strength,
    )


def _atr_fact(value: float = 50.0) -> ATRFact:
    return ATRFact(
        timestamp=BASE,
        evidence=(
            EvidenceEntry(
                text=f"ATR14 = {value:.2f}",
                level=EvidenceLevel.INFO,
                source="ATRAnalyzer",
            ),
        ),
        value=value,
        period=14,
    )


def _keyed_facts(
    pullback: PullbackFact | None = None,
    trend: TrendFact | None = None,
    atr: ATRFact | None = None,
) -> dict[FactKey, Fact]:
    facts: dict[FactKey, Fact] = {}
    if pullback is not None:
        facts[FactKey("pullback_pattern")] = pullback
    if trend is not None:
        facts[FactKey("trend")] = trend
    if atr is not None:
        facts[FactKey("atr_14")] = atr
    return facts


class TestTradeSignal:
    def test_frozen(self) -> None:
        ts = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(52900.0, 53400.0),
            confidence=0.72,
            source="PullbackSignal",
            evidence=(),
        )
        assert ts.direction == TrendDirection.BULLISH
        assert ts.entry_zone == (52900.0, 53400.0)
        assert ts.confidence == 0.72
        assert ts.source == "PullbackSignal"

    def test_immutability(self) -> None:
        ts = TradeSignal(
            direction=TrendDirection.BEARISH,
            entry_zone=(50000.0, 51000.0),
            confidence=0.5,
            source="test",
            evidence=(),
        )
        try:
            ts.direction = TrendDirection.BULLISH  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass


class TestPullbackSignal:
    def test_confirmed_bullish_returns_signal(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        result = signal.evaluate(
            view,
            _keyed_facts(
                _bullish_pullback_fact(),
                _bullish_trend_fact(),
                _atr_fact(50.0),
            ),
        )
        assert result is not None
        assert result.direction == TrendDirection.BULLISH
        assert result.confidence > 0
        assert result.source == "PullbackSignal"

    def test_timeframe_qualified_facts_resolve(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        facts = {
            FactKey("pullback_pattern", timeframe=Timeframe.D1): _bullish_pullback_fact(),
            FactKey("trend", timeframe=Timeframe.D1): _bullish_trend_fact(),
            FactKey("atr_14", timeframe=Timeframe.D1): _atr_fact(50.0),
        }
        result = signal.evaluate(view, facts)
        assert result is not None
        assert result.direction == TrendDirection.BULLISH

    def test_confirmed_bearish_returns_signal(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        result = signal.evaluate(
            view,
            _keyed_facts(
                _bearish_pullback_fact(),
                _bearish_trend_fact(),
                _atr_fact(50.0),
            ),
        )
        assert result is not None
        assert result.direction == TrendDirection.BEARISH

    def test_neutral_direction_returns_none(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        result = signal.evaluate(
            view,
            _keyed_facts(
                _neutral_pullback_fact(),
                _bullish_trend_fact(),
                _atr_fact(50.0),
            ),
        )
        assert result is None

    def test_empty_swing_pattern_returns_none(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        result = signal.evaluate(
            view,
            _keyed_facts(
                _weak_pullback_fact(),
                _bullish_trend_fact(),
                _atr_fact(50.0),
            ),
        )
        assert result is None

    def test_missing_pullback_returns_none(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        result = signal.evaluate(view, _keyed_facts())
        assert result is None

    def test_missing_trend_returns_none(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        result = signal.evaluate(
            view,
            _keyed_facts(pullback=_bullish_pullback_fact()),
        )
        assert result is None

    def test_missing_atr_returns_none(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        result = signal.evaluate(
            view,
            _keyed_facts(
                pullback=_bullish_pullback_fact(),
                trend=_bullish_trend_fact(),
            ),
        )
        assert result is None

    def test_entry_zone_around_current_price(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        result = signal.evaluate(
            view,
            _keyed_facts(
                _bullish_pullback_fact(),
                _bullish_trend_fact(),
                _atr_fact(100.0),
            ),
        )
        assert result is not None
        lo, hi = result.entry_zone
        assert lo < 100.0 < hi
        assert hi - lo == 100.0  # 0.5 * ATR * 2

    def test_confidence_reflects_trend_strength(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        strong = signal.evaluate(
            view,
            _keyed_facts(
                _bullish_pullback_fact(),
                _bullish_trend_fact(strength=0.9),
                _atr_fact(50.0),
            ),
        )
        weak = signal.evaluate(
            view,
            _keyed_facts(
                _bullish_pullback_fact(),
                _bullish_trend_fact(strength=0.3),
                _atr_fact(50.0),
            ),
        )
        assert strong is not None
        assert weak is not None
        assert strong.confidence > weak.confidence

    def test_min_strength_filter(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal(min_strength=0.9)
        result = signal.evaluate(
            view,
            _keyed_facts(
                _bullish_pullback_fact(),  # strength=0.72
                _bullish_trend_fact(),
                _atr_fact(50.0),
            ),
        )
        assert result is None

    def test_evidence_populated(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal()
        result = signal.evaluate(
            view,
            _keyed_facts(
                _bullish_pullback_fact(),
                _bullish_trend_fact(),
                _atr_fact(50.0),
            ),
        )
        assert result is not None
        assert len(result.evidence) >= 2
        assert any("pullback detected" in e.text.lower() for e in result.evidence)
        assert any("entry zone" in e.text.lower() for e in result.evidence)

    def test_custom_keys(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signal = PullbackSignal(pullback_key="my_pullback", trend_key="my_trend", atr_key="my_atr")
        facts = {
            FactKey("my_pullback"): _bullish_pullback_fact(),
            FactKey("my_trend"): _bullish_trend_fact(),
            FactKey("my_atr"): _atr_fact(50.0),
        }
        result = signal.evaluate(view, facts)
        assert result is not None

    def test_readahead_safety(self) -> None:
        """Adding future candles doesn't change signal evaluation."""
        candles_data = _flat_candles()
        store1 = _make_store(candles_data)
        view1 = MarketView(store1, cursor=49, window_size=50)
        signal = PullbackSignal()
        facts = _keyed_facts(
            _bullish_pullback_fact(),
            _bullish_trend_fact(),
            _atr_fact(50.0),
        )
        result1 = signal.evaluate(view1, facts)

        candles_data2 = candles_data + [(200.0, 210.0, 190.0, 200.0, 5000.0)]
        store2 = _make_store(candles_data2)
        view2 = MarketView(store2, cursor=49, window_size=50)
        result2 = signal.evaluate(view2, facts)

        assert result1 is not None
        assert result2 is not None
        assert result1.direction == result2.direction
        assert result1.entry_zone == result2.entry_zone
        assert result1.confidence == result2.confidence


class TestStrategy:
    def test_build_from_config(self) -> None:
        config = StrategyConfig(
            name="test_strategy",
            version="1.0",
            analyzers=(AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),),
            signals=(SignalConfig(type="PullbackSignal", rules={"min_strength": 0.6}),),
        )
        strategy = Strategy("test", config)
        assert strategy.name == "test"
        assert strategy.graph is not None
        assert len(strategy.graph.execution_order()) == 1

    def test_evaluate_returns_signals(self) -> None:
        config = StrategyConfig(
            name="test_strategy",
            version="1.0",
            analyzers=(),
            signals=(SignalConfig(type="PullbackSignal", rules={}),),
        )
        strategy = Strategy("test", config)
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        facts = _keyed_facts(
            _bullish_pullback_fact(),
            _bullish_trend_fact(),
            _atr_fact(50.0),
        )
        signals = strategy.evaluate(view, facts)
        assert len(signals) == 1
        assert signals[0].direction == TrendDirection.BULLISH

    def test_evaluate_returns_empty_when_no_signal(self) -> None:
        config = StrategyConfig(
            name="test_strategy",
            version="1.0",
            analyzers=(),
            signals=(SignalConfig(type="PullbackSignal", rules={}),),
        )
        strategy = Strategy("test", config)
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        facts = _keyed_facts(
            _neutral_pullback_fact(),
            _bullish_trend_fact(),
            _atr_fact(50.0),
        )
        signals = strategy.evaluate(view, facts)
        assert len(signals) == 0

    def test_unknown_signal_type_raises(self) -> None:
        config = StrategyConfig(
            name="test_strategy",
            version="1.0",
            analyzers=(),
            signals=(SignalConfig(type="NonexistentSignal", rules={}),),
        )
        try:
            Strategy("test", config)
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "NonexistentSignal" in str(e)

    def test_no_signals_config(self) -> None:
        config = StrategyConfig(
            name="test_strategy",
            version="1.0",
            analyzers=(),
            signals=(),
        )
        strategy = Strategy("test", config)
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        signals = strategy.evaluate(view, {})
        assert len(signals) == 0


class TestStrategyConfigLoading:
    def _write_yaml(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "strategy.yaml"
        p.write_text(content)
        return p

    def test_load_strategy_with_signals(self, tmp_path: Path) -> None:
        yaml_content = """\
strategy:
  name: pullback_test
  version: "1.0"
analyzers:
  - type: EMAAnalyzer
    params:
      period: 20
  - type: EMAAnalyzer
    params:
      period: 50
  - type: ATRAnalyzer
  - type: TrendAnalyzer
  - type: BasicSwingAnalyzer
    params:
      lookback: 50
  - type: SwingStructureAnalyzer
    params:
      window: 20
  - type: PullbackPatternAnalyzer
signals:
  - type: PullbackSignal
    requires:
      - pullback_pattern
    rules:
      min_strength: 0.5
"""
        path = self._write_yaml(tmp_path, yaml_content)
        config = load_strategy(path)
        assert config.name == "pullback_test"
        assert len(config.signals) == 1
        assert config.signals[0].type == "PullbackSignal"
        assert config.signals[0].requires == ("pullback_pattern",)
        assert config.signals[0].rules == {"min_strength": 0.5}

    def test_validate_config_passes(self, tmp_path: Path) -> None:
        yaml_content = """\
strategy:
  name: test
analyzers:
  - type: BasicSwingAnalyzer
    params:
      lookback: 50
  - type: SwingStructureAnalyzer
    params:
      window: 20
  - type: PullbackPatternAnalyzer
signals:
  - type: PullbackSignal
    requires:
      - pullback_pattern
"""
        path = self._write_yaml(tmp_path, yaml_content)
        config = load_strategy(path)
        errors = validate_config(config)
        assert len(errors) == 0

    def test_strategy_evaluate_full_pipeline(self, tmp_path: Path) -> None:
        yaml_content = """\
strategy:
  name: pullback_test
  version: "1.0"
analyzers: []
signals:
  - type: PullbackSignal
    rules:
      min_strength: 0.5
"""
        path = self._write_yaml(tmp_path, yaml_content)
        config = load_strategy(path)
        strategy = Strategy("pullback_test", config)

        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        facts = _keyed_facts(
            _bullish_pullback_fact(),
            _bullish_trend_fact(),
            _atr_fact(50.0),
        )
        signals = strategy.evaluate(view, facts)
        assert len(signals) == 1
        assert signals[0].direction == TrendDirection.BULLISH
        assert signals[0].confidence > 0
