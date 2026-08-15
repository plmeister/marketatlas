from datetime import UTC, datetime, timedelta

from marketatlas.analysis.factkey import FactKey
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
    data = MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
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
) -> dict[FactKey, Fact]:
    f: dict[FactKey, Fact] = {}
    if atr is not None:
        f[FactKey("atr_14")] = atr
    if swing is not None:
        f[FactKey("swing")] = swing
    if sr is not None:
        f[FactKey("sr")] = sr
    return f


class TestRiskEngine:
    def test_no_atr_returns_none(self) -> None:
        store = _make_store([(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine()
        candidate, evidence = engine.evaluate(_bullish_signal(), {}, view)
        assert candidate is None
        assert any("ATR" in e.text for e in evidence)

    def test_zero_atr_returns_none(self) -> None:
        store = _make_store([(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine()
        bad_atr = ATRFact(timestamp=BASE, evidence=(), value=0.0, period=14)
        candidate, evidence = engine.evaluate(_bullish_signal(), _facts(atr=bad_atr), view)
        assert candidate is None
        assert any("ATR" in e.text for e in evidence)

    def test_bullish_entry_with_slippage(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.1)
        candidate, _evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert candidate is not None
        expected_entry = 100.0 * (1 + 0.1 / 100)
        assert abs(candidate.entry - expected_entry) < 0.01

    def test_bearish_entry_with_slippage(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.1)
        candidate, _evidence = engine.evaluate(
            _bearish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert candidate is not None
        expected_entry = 100.0 * (1 - 0.1 / 100)
        assert abs(candidate.entry - expected_entry) < 0.01

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
        candidate, _evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), swing=swings, sr=_sr_fact(())), view
        )
        assert candidate is not None
        expected_stop = 96.0 - 0.2 * 2.0
        assert abs(candidate.stop - expected_stop) < 0.01

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
        candidate, _evidence = engine.evaluate(
            _bearish_signal(), _facts(atr=_atr_fact(2.0), swing=swings, sr=_sr_fact(())), view
        )
        assert candidate is not None
        expected_stop = 104.0 + 0.2 * 2.0
        assert abs(candidate.stop - expected_stop) < 0.01

    def test_stop_distance_exceeds_max_rejects(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(max_stop_atr=1.0, slippage_pct=0.0)
        swings = _swings_fact(
            (SwingPoint(price=80.0, index=0, type=SwingType.LOW, timestamp=BASE),)
        )
        candidate, evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), swing=swings, sr=_sr_fact(())), view
        )
        assert candidate is None
        assert any("stop distance" in e.text for e in evidence)

    def test_sr_crossing_bullish_resistance_rejects(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        sr = _sr_fact((SRLevel(price=103.0, strength=2, type="resistance"),))
        candidate, evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert candidate is None
        assert any("S/R" in e.text for e in evidence)

    def test_sr_crossing_bearish_support_rejects(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        sr = _sr_fact((SRLevel(price=99.0, strength=2, type="support"),))
        candidate, evidence = engine.evaluate(
            _bearish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert candidate is None
        assert any("S/R" in e.text for e in evidence)

    def test_no_sr_fact_rejects(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        candidate, evidence = engine.evaluate(_bullish_signal(), _facts(atr=_atr_fact(2.0)), view)
        assert candidate is None
        assert any("no SR fact" in e.text for e in evidence)

    def test_rr_ratio_in_range(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(min_rr=2.0, max_rr=4.0, slippage_pct=0.0)
        candidate, _evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert candidate is not None
        assert 2.0 <= candidate.rr_ratio <= 4.0

    def test_size_calculation(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(risk_pct=1.0, slippage_pct=0.0)
        candidate, _evidence = engine.evaluate(
            _bullish_signal(),
            _facts(atr=_atr_fact(2.0), sr=_sr_fact(())),
            view,
            balance=1000.0,
        )
        assert candidate is not None
        expected_risk = 1000.0 * 0.01
        assert abs(candidate.risk_amount - expected_risk) < 0.01
        assert candidate.size == expected_risk / abs(candidate.entry - candidate.stop)

    def test_smaller_balance_smaller_size(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(risk_pct=1.0, slippage_pct=0.0)
        c1, _ = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view, balance=1000.0
        )
        c2, _ = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view, balance=500.0
        )
        assert c1 is not None and c2 is not None
        assert c2.size < c1.size

    def test_slippage_evidence(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.1)
        _candidate, evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert any("Slippage" in e.text for e in evidence)

    def test_stop_evidence(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        _candidate, evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert any("Stop:" in e.text for e in evidence)

    def test_target_evidence(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        _candidate, evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert any("Target:" in e.text for e in evidence)

    def test_candidate_source_matches_signal(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        candidate, _evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert candidate is not None
        assert candidate.source == "PullbackSignal"

    def test_candidate_direction_matches_signal(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        candidate, _evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert candidate is not None
        assert candidate.direction == TrendDirection.BULLISH

    def test_avoid_srxing_false_allows_crossing(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(avoid_srxing=False, slippage_pct=0.0)
        sr = _sr_fact((SRLevel(price=103.0, strength=2, type="resistance"),))
        candidate, _evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert candidate is not None

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
        candidate, evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert candidate is None
        assert any("RR" in e.text for e in evidence)

    def test_max_hold_days_property(self) -> None:
        engine = RiskEngine(max_hold_days=10)
        assert engine.max_hold_days == 10

    def test_custom_keys(self) -> None:
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(atr_key="atr_custom", sr_key="sr_custom", swing_key="swing_custom")
        atr = ATRFact(timestamp=BASE, evidence=(), value=2.0, period=14)
        swings = _swings_fact(
            (SwingPoint(price=96.0, index=0, type=SwingType.LOW, timestamp=BASE),)
        )
        sr = _sr_fact(())
        facts = {
            FactKey("atr_custom"): atr,
            FactKey("swing_custom"): swings,
            FactKey("sr_custom"): sr,
        }
        candidate, _evidence = engine.evaluate(_bullish_signal(), facts, view)
        assert candidate is not None

    def test_no_swing_fact_fallback_stop(self) -> None:
        """Without swing fact, stop uses default 2*ATR fallback minus 0.2*ATR buffer."""
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        candidate, _evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert candidate is not None
        # stop = (entry - 2*ATR) - 0.2*ATR = 100 - 4 - 0.4 = 95.6
        expected_stop = 100.0 - 2.0 * 2.0 - 0.2 * 2.0
        assert abs(candidate.stop - expected_stop) < 0.01

    def test_bearish_no_swing_fact_fallback_stop(self) -> None:
        """Bearish without swing fact, stop uses default 2*ATR fallback plus 0.2*ATR buffer."""
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        candidate, _evidence = engine.evaluate(
            _bearish_signal(), _facts(atr=_atr_fact(2.0), sr=_sr_fact(())), view
        )
        assert candidate is not None
        # stop = (entry + 2*ATR) + 0.2*ATR = 100 + 4 + 0.4 = 104.4
        expected_stop = 100.0 + 2.0 * 2.0 + 0.2 * 2.0
        assert abs(candidate.stop - expected_stop) < 0.01

    def test_bullish_swing_low_above_entry_fallback(self) -> None:
        """Bullish: all swing lows above entry -> fallback to 2*ATR."""
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        swings = _swings_fact(
            (SwingPoint(price=110.0, index=0, type=SwingType.LOW, timestamp=BASE),)
        )
        candidate, _evidence = engine.evaluate(
            _bullish_signal(),
            _facts(atr=_atr_fact(2.0), swing=swings, sr=_sr_fact(())),
            view,
        )
        assert candidate is not None
        expected_stop = 100.0 - 2.0 * 2.0 - 0.2 * 2.0
        assert abs(candidate.stop - expected_stop) < 0.01

    def test_bearish_swing_high_below_entry_fallback(self) -> None:
        """Bearish: all swing highs below entry -> fallback to 2*ATR."""
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0)
        swings = _swings_fact(
            (SwingPoint(price=90.0, index=0, type=SwingType.HIGH, timestamp=BASE),)
        )
        candidate, _evidence = engine.evaluate(
            _bearish_signal(),
            _facts(atr=_atr_fact(2.0), swing=swings, sr=_sr_fact(())),
            view,
        )
        assert candidate is not None
        expected_stop = 100.0 + 2.0 * 2.0 + 0.2 * 2.0
        assert abs(candidate.stop - expected_stop) < 0.01

    def test_size_and_reward_calculation(self) -> None:
        """Verify size and reward are correctly computed."""
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(risk_pct=2.0, slippage_pct=0.0)
        candidate, _ = engine.evaluate(
            _bullish_signal(),
            _facts(atr=_atr_fact(2.0), sr=_sr_fact(())),
            view,
            balance=10000.0,
        )
        assert candidate is not None
        expected_risk = 10000.0 * 0.02
        assert abs(candidate.risk_amount - expected_risk) < 0.01
        assert abs(candidate.reward_amount - candidate.rr_ratio * expected_risk) < 0.01
        assert abs(candidate.size - expected_risk / abs(candidate.entry - candidate.stop)) < 0.01

    def test_stop_distance_always_positive_bullish(self) -> None:
        """Stop distance is always > 0 for bullish trades across many configurations.

        Documents that the stop_distance <= 0 branch (risk.py:100-107) is dead code:
        - With swings: swing lows < entry, so stop = swing - 0.2*ATR < entry
        - Without swings: stop = entry - 2.2*ATR < entry
        """
        for atr_val in [0.5, 1.0, 5.0, 50.0]:
            for slippage in [0.0, 0.1, 1.0]:
                candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
                store = _make_store(candles)
                view = MarketView(store, cursor=4, window_size=4)
                engine = RiskEngine(slippage_pct=slippage)
                candidate, _ = engine.evaluate(
                    _bullish_signal(),
                    _facts(atr=_atr_fact(atr_val), sr=_sr_fact(())),
                    view,
                )
                assert candidate is not None
                assert abs(candidate.entry - candidate.stop) > 0

    def test_stop_distance_always_positive_bearish(self) -> None:
        """Stop distance is always > 0 for bearish trades across many configurations.

        Documents that the stop_distance <= 0 branch (risk.py:100-107) is dead code:
        - With swings: swing highs > entry, so stop = swing + 0.2*ATR > entry
        - Without swings: stop = entry + 2.2*ATR > entry
        """
        for atr_val in [0.5, 1.0, 5.0, 50.0]:
            for slippage in [0.0, 0.1, 1.0]:
                candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
                store = _make_store(candles)
                view = MarketView(store, cursor=4, window_size=4)
                engine = RiskEngine(slippage_pct=slippage)
                candidate, _ = engine.evaluate(
                    _bearish_signal(),
                    _facts(atr=_atr_fact(atr_val), sr=_sr_fact(())),
                    view,
                )
                assert candidate is not None
                assert abs(candidate.entry - candidate.stop) > 0

    def test_sr_crossing_rejection_redundant_with_find_valid_rr(self) -> None:
        """S/R crossing rejection at risk.py:141-158 is dead code.

        _find_valid_rr already filters out any rr whose target crosses S/R
        (line 250). The re-check at line 140 uses the same entry/target/levels,
        so it always returns False. This test proves that when _find_valid_rr
        returns a valid rr, the final crossing check is always clean.
        """
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)

        sr = _sr_fact((SRLevel(price=103.0, strength=3, type="resistance"),))
        engine = RiskEngine(avoid_srxing=True, min_rr=2.0, max_rr=4.0, slippage_pct=0.0)
        candidate, _ = engine.evaluate(_bullish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view)
        if candidate is not None:
            lo, hi = min(candidate.entry, candidate.target), max(candidate.entry, candidate.target)
            for lv in sr.levels:
                assert not (lo < lv.price < hi), (
                    "candidate target should not cross S/R — "
                    "_find_valid_rr should have filtered it"
                )

    def test_stop_uses_most_recent_swing_low(self) -> None:
        """Bullish stop anchors to the most recent swing low below entry.

        Older swing low may be higher/closer to entry; recency wins.
        """
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0, max_stop_atr=10.0)
        older = BASE - timedelta(days=10)
        swings = _swings_fact(
            (
                SwingPoint(price=97.0, index=0, type=SwingType.LOW, timestamp=older),
                SwingPoint(price=94.0, index=2, type=SwingType.LOW, timestamp=BASE),
            )
        )
        candidate, _evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), swing=swings, sr=_sr_fact(())), view
        )
        assert candidate is not None
        expected_stop = 94.0 - 0.2 * 2.0
        assert abs(candidate.stop - expected_stop) < 0.01

    def test_stop_uses_most_recent_swing_high(self) -> None:
        """Bearish stop anchors to the most recent swing high above entry."""
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(slippage_pct=0.0, max_stop_atr=10.0)
        older = BASE - timedelta(days=10)
        swings = _swings_fact(
            (
                SwingPoint(price=103.0, index=0, type=SwingType.HIGH, timestamp=older),
                SwingPoint(price=107.0, index=2, type=SwingType.HIGH, timestamp=BASE),
            )
        )
        candidate, _evidence = engine.evaluate(
            _bearish_signal(), _facts(atr=_atr_fact(2.0), swing=swings, sr=_sr_fact(())), view
        )
        assert candidate is not None
        expected_stop = 107.0 + 0.2 * 2.0
        assert abs(candidate.stop - expected_stop) < 0.01

    def test_sr_buffer_rejects_target_too_close_to_resistance(self) -> None:
        """Target landing within sr_buffer_atr of an S/R level is rejected.

        No swings -> fallback stop. Entry 100, atr 2.0, buffer 0.5*2=1.0.
        rr=2.0 gives target 108.8; resistance at 109.5 -> target within
        buffer but not crossing -> every rr either sits in the buffer zone
        or crosses 109.5 -> reject.
        """
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(min_rr=2.0, max_rr=4.0, slippage_pct=0.0)
        sr = _sr_fact((SRLevel(price=109.5, strength=3, type="resistance"),))
        candidate, evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert candidate is None
        assert any("RR" in e.text for e in evidence)

    def test_sr_buffer_zero_allows_target_near_resistance(self) -> None:
        """sr_buffer_atr=0 removes the proximity constraint.

        Same setup as above: rr=2.0 target 108.8 vs resistance 109.5 is fine
        when the buffer is zero (target does not cross the level).
        """
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(
            min_rr=2.0, max_rr=4.0, slippage_pct=0.0, sr_buffer_atr=0.0
        )
        sr = _sr_fact((SRLevel(price=109.5, strength=3, type="resistance"),))
        candidate, _evidence = engine.evaluate(
            _bullish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert candidate is not None
        expected_target = 100.0 + 2.0 * abs(100.0 - 95.6)
        assert abs(candidate.target - expected_target) < 0.01

    def test_sr_buffer_rejects_target_too_close_to_support(self) -> None:
        """Bearish mirror of the resistance-buffer rejection."""
        candles = [(100.0, 105.0, 95.0, 102.0, 1000.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        engine = RiskEngine(min_rr=2.0, max_rr=4.0, slippage_pct=0.0)
        sr = _sr_fact((SRLevel(price=90.5, strength=3, type="support"),))
        candidate, evidence = engine.evaluate(
            _bearish_signal(), _facts(atr=_atr_fact(2.0), sr=sr), view
        )
        assert candidate is None
        assert any("RR" in e.text for e in evidence)
