from datetime import UTC, datetime
from typing import cast

from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import (
    SRFact,
    SRLevel,
    SwingFact,
    SwingPoint,
    SwingType,
    TrendDirection,
)
from marketatlas.strategy.risk import RiskEngine
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.trade import TradeCandidate

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _make_store(
    candles_data: list[tuple[float, float, float, float, float]],
) -> MarketStore:
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
    data = MarketData(
        symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles
    )
    return MarketStore(data)


def _atr_fact(value: float = 2.0) -> ATRFact:
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


def _swings_fact(swings: tuple[SwingPoint, ...]) -> SwingFact:
    return SwingFact(timestamp=BASE, evidence=(), swings=swings)


def _sr_fact(levels: tuple[SRLevel, ...]) -> SRFact:
    return SRFact(timestamp=BASE, evidence=(), levels=levels)


def _bullish_signal() -> TradeSignal:
    return TradeSignal(
        direction=TrendDirection.BULLISH,
        entry_zone=(99.0, 101.0),
        confidence=0.7,
        source="PullbackSignal",
        evidence=(),
    )


def _bearish_signal() -> TradeSignal:
    return TradeSignal(
        direction=TrendDirection.BEARISH,
        entry_zone=(99.0, 101.0),
        confidence=0.7,
        source="PullbackSignal",
        evidence=(),
    )


def _facts(
    atr: ATRFact | None = None,
    swing: SwingFact | None = None,
    sr: SRFact | None = None,
) -> dict[tuple[type[Fact], str], Fact]:
    f: dict[tuple[type[Fact], str], Fact] = {}
    if atr is not None:
        f[(ATRFact, "atr_14")] = atr
    if swing is not None:
        f[(SwingFact, "swing")] = swing
    if sr is not None:
        f[(SRFact, "sr")] = sr
    return f


class TestRiskEngine:
    def test_no_atr_returns_none(self) -> None:
        store = _make_store([(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine()
        result = engine.evaluate(_bullish_signal(), {}, view)
        assert result is None

    def test_zero_atr_returns_none(self) -> None:
        store = _make_store([(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine()
        bad_atr = ATRFact(timestamp=BASE, evidence=(), value=0.0, period=14)
        result = engine.evaluate(_bullish_signal(), _facts(atr=bad_atr), view)
        assert result is None

    def test_bullish_entry_with_slippage(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.1)
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view
        )
        assert result is not None
        expected_entry = 100.0 * (1 + 0.1 / 100)
        assert abs(result.entry - expected_entry) < 0.01

    def test_bearish_entry_with_slippage(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.1)
        result = engine.evaluate(
            _bearish_signal(), _facts(atr=_atr_fact(2.0)), view
        )
        assert result is not None
        expected_entry = 100.0 * (1 - 0.1 / 100)
        assert abs(result.entry - expected_entry) < 0.01

    def test_bullish_stop_below_swing_low(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        swings = _swings_fact(
            (
                SwingPoint(price=96.0, index=0, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=104.0, index=2, type=SwingType.HIGH, timestamp=BASE),
            )
        )
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), swing=swings), view
        )
        assert result is not None
        expected_stop = 96.0 - 0.2 * 2.0
        assert abs(result.stop - expected_stop) < 0.01

    def test_bearish_stop_above_swing_high(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        swings = _swings_fact(
            (
                SwingPoint(price=104.0, index=0, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=96.0, index=2, type=SwingType.LOW, timestamp=BASE),
            )
        )
        result = engine.evaluate(
            _bearish_signal(), _facts(atr=_atr_fact(2.0), swing=swings), view
        )
        assert result is not None
        expected_stop = 104.0 + 0.2 * 2.0
        assert abs(result.stop - expected_stop) < 0.01

    def test_stop_distance_exceeds_max_rejects(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(max_stop_atr=1.0, slippage_pct=0.0)
        swings = _swings_fact(
            (SwingPoint(price=80.0, index=0, type=SwingType.LOW, timestamp=BASE),)
        )
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), swing=swings), view
        )
        assert result is None

    def test_sr_crossing_bullish_resistance_rejects(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        sr = _sr_fact(
            (SRLevel(price=103.0, strength=2, type="resistance"),)
        )
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert result is None

    def test_sr_crossing_bearish_support_rejects(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        sr = _sr_fact(
            (SRLevel(price=99.0, strength=2, type="support"),)
        )
        result = engine.evaluate(
            _bearish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert result is None

    def test_no_sr_levels_no_crossing_check(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view
        )
        assert result is not None

    def test_rr_ratio_in_range(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(min_rr=2.0, max_rr=4.0, slippage_pct=0.0)
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view
        )
        assert result is not None
        assert 2.0 <= result.rr_ratio <= 4.0

    def test_size_calculation(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(risk_pct=1.0, slippage_pct=0.0)
        result = engine.evaluate(
            _bullish_signal(),
            _facts(atr=_atr_fact(2.0)),
            view,
            balance=1000.0,
        )
        assert result is not None
        expected_risk = 1000.0 * 0.01
        assert abs(result.risk_amount - expected_risk) < 0.01
        assert result.size == expected_risk / abs(result.entry - result.stop)

    def test_smaller_balance_smaller_size(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(risk_pct=1.0, slippage_pct=0.0)
        r1 = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view, balance=1000.0
        )
        r2 = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view, balance=500.0
        )
        assert r1 is not None and r2 is not None
        assert r2.size < r1.size

    def test_slippage_evidence(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.1)
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view
        )
        assert result is not None
        assert any("Slippage" in e.text for e in result.evidence)

    def test_stop_evidence(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view
        )
        assert result is not None
        assert any("Stop:" in e.text for e in result.evidence)

    def test_target_evidence(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view
        )
        assert result is not None
        assert any("Target:" in e.text for e in result.evidence)

    def test_candidate_source_matches_signal(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view
        )
        assert result is not None
        assert result.source == "PullbackSignal"

    def test_candidate_direction_matches_signal(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0)), view
        )
        assert result is not None
        assert result.direction == TrendDirection.BULLISH

    def test_avoid_srxing_false_allows_crossing(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(avoid_srxing=False, slippage_pct=0.0)
        sr = _sr_fact(
            (SRLevel(price=103.0, strength=2, type="resistance"),)
        )
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert result is not None

    def test_no_valid_rr_rejects(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(min_rr=2.0, max_rr=4.0, slippage_pct=0.0)
        sr = _sr_fact(
            (
                SRLevel(price=105.0, strength=3, type="resistance"),
                SRLevel(price=110.0, strength=2, type="resistance"),
                SRLevel(price=115.0, strength=1, type="resistance"),
            )
        )
        result = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert result is None

    def test_max_hold_days_property(self) -> None:
        engine = RiskEngine(max_hold_days=10)
        assert engine.max_hold_days == 10

    def test_custom_keys(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(
            atr_key="atr_custom", sr_key="sr_custom", swing_key="swing_custom"
        )
        atr = ATRFact(timestamp=BASE, evidence=(), value=2.0, period=14)
        swings = _swings_fact(
            (SwingPoint(price=96.0, index=0, type=SwingType.LOW, timestamp=BASE),)
        )
        facts = cast(
            dict[tuple[type[Fact], str], Fact],
            {
                (ATRFact, "atr_custom"): atr,
                (SwingFact, "swing_custom"): swings,
            },
        )
        result = engine.evaluate(_bullish_signal(), facts, view)
        assert result is not None
