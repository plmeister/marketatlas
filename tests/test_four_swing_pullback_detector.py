from datetime import UTC, datetime
from typing import cast

from marketatlas.analysis.analyzers.atr import ATRAnalyzer
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.analyzers.swing import SwingStructureAnalyzer
from marketatlas.analysis.analyzers.trend import TrendAnalyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.analysis.patterns.four_swing_pullback import FourSwingPullbackDetector
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.pattern import PullbackFact, PullbackStatus
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import (
    SwingFact,
    SwingPoint,
    SwingType,
    TrendDirection,
    TrendFact,
)

BASE = datetime(2024, 1, 1, tzinfo=UTC)

CandleTuple = tuple[float, float, float, float, float]


def _make_store(candles_data: list[CandleTuple]) -> MarketStore:
    candles = tuple(
        Candle(timestamp=BASE, open=o, high=h, low=lo, close=c, volume=v)
        for o, h, lo, c, v in candles_data
    )
    data = MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
    return MarketStore(data)


def _bullish_trend_fact() -> TrendFact:
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
        strength=0.7,
    )


def _bearish_trend_fact() -> TrendFact:
    return TrendFact(
        timestamp=BASE,
        evidence=(
            EvidenceEntry(
                text="Trend: Bearish",
                level=EvidenceLevel.INFO,
                source="TrendAnalyzer",
            ),
        ),
        direction=TrendDirection.BEARISH,
        strength=0.7,
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


def _keyed_facts(swing: SwingFact, trend: TrendFact, atr: ATRFact) -> dict[FactKey, Fact]:
    return {
        FactKey("swing"): swing,
        FactKey("trend"): trend,
        FactKey("atr_14"): atr,
    }


def _bullish_4swing_fact() -> SwingFact:
    """HL(48200) HH(51500) HL(49100) HH(52800) — clean bullish pattern."""
    return SwingFact(
        timestamp=BASE,
        evidence=(),
        swings=(
            SwingPoint(price=48200.0, index=10, type=SwingType.LOW, timestamp=BASE),
            SwingPoint(price=51500.0, index=20, type=SwingType.HIGH, timestamp=BASE),
            SwingPoint(price=49100.0, index=30, type=SwingType.LOW, timestamp=BASE),
            SwingPoint(price=52800.0, index=40, type=SwingType.HIGH, timestamp=BASE),
        ),
    )


def _bearish_4swing_fact() -> SwingFact:
    """LH(52000) LL(49000) LH(51000) LL(48000) — clean bearish pattern."""
    return SwingFact(
        timestamp=BASE,
        evidence=(),
        swings=(
            SwingPoint(price=52000.0, index=10, type=SwingType.HIGH, timestamp=BASE),
            SwingPoint(price=49000.0, index=20, type=SwingType.LOW, timestamp=BASE),
            SwingPoint(price=51000.0, index=30, type=SwingType.HIGH, timestamp=BASE),
            SwingPoint(price=48000.0, index=40, type=SwingType.LOW, timestamp=BASE),
        ),
    )


def _non_matching_swing_fact() -> SwingFact:
    """LH/HL/HH/LL — not a valid pattern."""
    return SwingFact(
        timestamp=BASE,
        evidence=(),
        swings=(
            SwingPoint(price=52000.0, index=10, type=SwingType.HIGH, timestamp=BASE),
            SwingPoint(price=49000.0, index=20, type=SwingType.LOW, timestamp=BASE),
            SwingPoint(price=53000.0, index=30, type=SwingType.HIGH, timestamp=BASE),
            SwingPoint(price=48000.0, index=40, type=SwingType.LOW, timestamp=BASE),
        ),
    )


def _bullish_4swing_with_extra() -> SwingFact:
    """6 swings, last 4 form bullish pattern."""
    return SwingFact(
        timestamp=BASE,
        evidence=(),
        swings=(
            SwingPoint(price=47000.0, index=1, type=SwingType.LOW, timestamp=BASE),
            SwingPoint(price=50000.0, index=5, type=SwingType.HIGH, timestamp=BASE),
            SwingPoint(price=48200.0, index=10, type=SwingType.LOW, timestamp=BASE),
            SwingPoint(price=51500.0, index=20, type=SwingType.HIGH, timestamp=BASE),
            SwingPoint(price=49100.0, index=30, type=SwingType.LOW, timestamp=BASE),
            SwingPoint(price=52800.0, index=40, type=SwingType.HIGH, timestamp=BASE),
        ),
    )


def _flat_candles(n: int = 50) -> list[CandleTuple]:
    return [(100.0, 101.0, 99.0, 100.0, 1000.0)] * n


def _linear_candles_between(
    swings: list[tuple[float, int]], candle_range: float = 2.0
) -> list[CandleTuple]:
    """Build candles that linearly interpolate between swing prices.

    swings: list of (price, store_index) for each swing point.
    Between swings, candle closes follow a straight line.
    """
    if not swings:
        return []
    max_idx = swings[-1][1]
    candles: list[CandleTuple] = []
    for i in range(max_idx + 1):
        # Find which segment this index falls in
        seg_start = swings[0]
        seg_end = swings[-1]
        for s_idx in range(len(swings) - 1):
            if swings[s_idx][1] <= i <= swings[s_idx + 1][1]:
                seg_start = swings[s_idx]
                seg_end = swings[s_idx + 1]
                break
        p1, i1 = seg_start
        p2, i2 = seg_end
        if i2 == i1:
            close = p1
        else:
            t = (i - i1) / (i2 - i1)
            close = p1 + t * (p2 - p1)
        o = close
        h = close + candle_range / 2
        lo = close - candle_range / 2
        candles.append((o, h, lo, close, 1000.0))
    return candles


def _bullish_linear_candles() -> list[CandleTuple]:
    """Candles following HL(48200@10) HH(51500@20) HL(49100@30) HH(52800@40) + extra."""
    return _linear_candles_between(
        [(48200.0, 10), (51500.0, 20), (49100.0, 30), (52800.0, 40)],
        candle_range=50.0,
    )


def _bearish_linear_candles() -> list[CandleTuple]:
    """Candles following LH(52000@10) LL(49000@20) LH(51000@30) LL(48000@40) + extra."""
    return _linear_candles_between(
        [(52000.0, 10), (49000.0, 20), (51000.0, 30), (48000.0, 40)],
        candle_range=50.0,
    )


class TestFourSwingPullbackDetector:
    def test_requires_swing_trend_atr(self) -> None:
        detector = FourSwingPullbackDetector()
        reqs = detector.requires()
        assert FactKey("swing") in reqs
        assert FactKey("trend") in reqs
        assert FactKey("atr_14") in reqs

    def test_produces_pullback_fact(self) -> None:
        detector = FourSwingPullbackDetector()
        assert detector.produces() == (FactKey("four_swing_pullback"),)

    def test_bullish_4swing_detected(self) -> None:
        candles = _bullish_linear_candles()
        store = _make_store(candles)
        n = len(candles)
        view = MarketView(store, cursor=n - 1, window_size=n)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED
        assert fact.direction == TrendDirection.BULLISH
        assert len(fact.swing_pattern) == 4
        assert fact.swing_pattern == (48200.0, 51500.0, 49100.0, 52800.0)

    def test_bearish_4swing_detected(self) -> None:
        candles = _bearish_linear_candles()
        store = _make_store(candles)
        n = len(candles)
        view = MarketView(store, cursor=n - 1, window_size=n)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bearish_4swing_fact(), _bearish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED
        assert fact.direction == TrendDirection.BEARISH
        assert fact.swing_pattern == (52000.0, 49000.0, 51000.0, 48000.0)

    def test_non_matching_pattern_invalidated(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_non_matching_swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_fewer_than_4_swings_invalidated(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=48200.0, index=10, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=51500.0, index=20, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_neutral_trend_invalidated(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        neutral = TrendFact(
            timestamp=BASE,
            evidence=(),
            direction=TrendDirection.NEUTRAL,
            strength=0.0,
        )
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), neutral, _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_zero_atr_invalidated(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(0.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_missing_facts_invalidated(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(view, {})
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_linearity_filter_clean_swings(self) -> None:
        candles = _bullish_linear_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles))
        detector = FourSwingPullbackDetector(max_deviation_pct=0.15)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.deviation_pct < 0.15

    def test_linearity_filter_rejects_choppy(self) -> None:
        """Build candles with a big spike between swings to exceed deviation threshold."""
        candles_data: list[CandleTuple] = []
        for i in range(40):
            if i < 5:
                candles_data.append((100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i, 1000.0))
            elif i < 15:
                offset = (i - 5) * 0.5
                candles_data.append(
                    (
                        105.0 + offset,
                        106.0 + offset,
                        104.0 + offset,
                        105.0 + offset,
                        1000.0,
                    )
                )
            elif i < 20:
                candles_data.append(
                    (
                        110.0,
                        130.0,
                        109.0,
                        110.0,
                        1000.0,
                    )
                )  # big spike
            elif i < 25:
                offset = (i - 20) * 0.5
                candles_data.append(
                    (
                        110.0 - offset,
                        111.0 - offset,
                        109.0 - offset,
                        110.0 - offset,
                        1000.0,
                    )
                )
            elif i < 35:
                offset = (i - 25) * 0.5
                candles_data.append(
                    (
                        103.0 + offset,
                        104.0 + offset,
                        102.0 + offset,
                        103.0 + offset,
                        1000.0,
                    )
                )
            else:
                candles_data.append((108.0, 109.0, 107.0, 108.0, 1000.0))

        store = _make_store(candles_data)
        view = MarketView(store, cursor=len(candles_data) - 1, window_size=len(candles_data))
        detector = FourSwingPullbackDetector(max_deviation_pct=0.05)
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=100.0, index=2, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=110.0, index=10, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=103.0, index=18, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=113.0, index=28, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(5.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_bullish_confirmation_candle(self) -> None:
        """Bullish: close > last swing high, strong body, high volume -> CONFIRMED."""
        base_candles = _bullish_linear_candles()
        # Add confirmation candle: close above 52800, strong body, high volume
        confirmation = [
            (52800.0, 53200.0, 52600.0, 53100.0, 1500.0),
            (53100.0, 53500.0, 53000.0, 53400.0, 1500.0),
        ]
        candles_data = base_candles + confirmation

        store = _make_store(candles_data)
        view = MarketView(store, cursor=len(candles_data) - 1, window_size=len(candles_data))

        detector = FourSwingPullbackDetector(
            confirmation_min_body_pct=0.5,
            confirmation_min_volume_ratio=1.1,
        )
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.CONFIRMED
        assert fact.confirmation_strength > 0.0

    def test_bullish_weak_body_not_confirmed(self) -> None:
        """Bullish: close > last swing but weak body -> DETECTED."""
        base_candles = _bullish_linear_candles()
        # Weak body: close barely above open
        confirmation = [
            (52800.0, 53100.0, 52700.0, 52850.0, 1000.0),
            (52850.0, 52900.0, 52800.0, 52860.0, 1000.0),
        ]
        candles_data = base_candles + confirmation

        store = _make_store(candles_data)
        view = MarketView(store, cursor=len(candles_data) - 1, window_size=len(candles_data))

        detector = FourSwingPullbackDetector(
            confirmation_min_body_pct=0.6,
            confirmation_min_volume_ratio=1.2,
        )
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED

    def test_bullish_close_below_last_swing_not_confirmed(self) -> None:
        """Bullish: close < last swing high -> DETECTED."""
        base_candles = _bullish_linear_candles()
        # Close below 52800
        confirmation = [
            (52500.0, 52600.0, 52400.0, 52500.0, 1000.0),
            (52500.0, 52600.0, 52400.0, 52500.0, 1000.0),
        ]
        candles_data = base_candles + confirmation

        store = _make_store(candles_data)
        view = MarketView(store, cursor=len(candles_data) - 1, window_size=len(candles_data))

        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED

    def test_bearish_confirmation_candle(self) -> None:
        """Bearish: close < last swing low, strong body, high volume -> CONFIRMED."""
        base_candles = _bearish_linear_candles()
        # Confirmation: close below 48000, strong body, high volume
        confirmation = [
            (48100.0, 48200.0, 47600.0, 47700.0, 1500.0),
            (47700.0, 47800.0, 47300.0, 47400.0, 1500.0),
        ]
        candles_data = base_candles + confirmation

        store = _make_store(candles_data)
        view = MarketView(store, cursor=len(candles_data) - 1, window_size=len(candles_data))

        detector = FourSwingPullbackDetector(
            confirmation_min_body_pct=0.5,
            confirmation_min_volume_ratio=1.1,
        )
        result = detector.analyze(
            view,
            _keyed_facts(_bearish_4swing_fact(), _bearish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.CONFIRMED
        assert fact.confirmation_strength > 0.0

    def test_bearish_close_above_last_swing_not_confirmed(self) -> None:
        """Bearish: close > last swing low -> DETECTED."""
        base_candles = _bearish_linear_candles()
        # Close above 48000
        confirmation = [
            (48500.0, 48600.0, 48400.0, 48500.0, 1000.0),
            (48500.0, 48600.0, 48400.0, 48500.0, 1000.0),
        ]
        candles_data = base_candles + confirmation

        store = _make_store(candles_data)
        view = MarketView(store, cursor=len(candles_data) - 1, window_size=len(candles_data))

        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bearish_4swing_fact(), _bearish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED

    def test_extra_swings_before_4swing(self) -> None:
        """6 swings, last 4 form valid pattern -> DETECTED."""
        candles = _bullish_linear_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles))
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_with_extra(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED

    def test_evidence_contains_pattern_description(self) -> None:
        candles = _bullish_linear_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles))
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        assert any("4-swing" in e.text.lower() for e in result.evidence)

    def test_evidence_contains_deviation_info(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        assert any("deviation" in e.text.lower() for e in result.evidence)

    def test_evidence_matches_fact_evidence(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        assert result.evidence == result.facts[0].evidence

    def test_fact_has_correct_timestamp(self) -> None:
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        assert result.facts[0].timestamp == BASE

    def test_custom_keys(self) -> None:
        candles = _bullish_linear_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles))
        detector = FourSwingPullbackDetector(
            swing_key="my_swing",
            trend_key="my_trend",
            atr_key="my_atr",
        )
        facts = {
            FactKey("my_swing"): _bullish_4swing_fact(),
            FactKey("my_trend"): _bullish_trend_fact(),
            FactKey("my_atr"): _atr_fact(50.0),
        }
        result = detector.analyze(view, facts)
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED

    def test_readahead_safety(self) -> None:
        """Changing future candles should not change current frame result."""
        candles_data = _flat_candles()
        store1 = _make_store(candles_data)
        view1 = MarketView(store1, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result1 = detector.analyze(
            view1,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )

        candles_data2 = candles_data + [(200.0, 210.0, 190.0, 200.0, 5000.0)]
        store2 = _make_store(candles_data2)
        view2 = MarketView(store2, cursor=49, window_size=50)
        result2 = detector.analyze(
            view2,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )

        f1 = cast(PullbackFact, result1.facts[0])
        f2 = cast(PullbackFact, result2.facts[0])
        assert f1.status == f2.status
        assert f1.swing_pattern == f2.swing_pattern

    def test_integration_with_graph(self) -> None:
        """FourSwingPullbackDetector works in an AnalysisGraph with SwingStructureAnalyzer."""
        candles_data: list[CandleTuple] = []
        base = 100.0
        for i in range(50):
            if i % 10 < 5:
                candles_data.append((base + i, base + i + 2, base + i - 1, base + i + 1, 1000.0))
            else:
                candles_data.append((base + i, base + i + 1, base + i - 2, base + i - 0.5, 1000.0))

        store = _make_store(candles_data)
        view = MarketView(store, cursor=49, window_size=50)

        graph = AnalysisGraph(
            [
                EMAAnalyzer(period=20),
                EMAAnalyzer(period=50),
                ATRAnalyzer(),
                TrendAnalyzer(),
                SwingStructureAnalyzer(lookback=50, min_swing_atr=0.3),
                FourSwingPullbackDetector(),
            ]
        )
        facts = graph.run(view)
        pullback = facts.get(FactKey("four_swing_pullback"))
        assert pullback is not None
        assert isinstance(pullback, PullbackFact)

    def test_invalidated_no_pullback_field_values(self) -> None:
        """Invalidated fact has zeroed-out pattern fields."""
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_non_matching_swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED
        assert fact.deviation_pct == 0.0
        assert fact.confirmation_strength == 0.0

    def test_higher_low_not_higher_invalidated(self) -> None:
        """Bullish: swing[2] low <= swing[0] low -> INVALIDATED."""
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=48200.0, index=10, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=51500.0, index=20, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=47800.0, index=30, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=52800.0, index=40, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_higher_high_not_higher_invalidated(self) -> None:
        """Bullish: swing[3] high <= swing[1] high -> INVALIDATED."""
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=48200.0, index=10, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=51500.0, index=20, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=49100.0, index=30, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=51000.0, index=40, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_bearish_lower_high_not_lower_invalidated(self) -> None:
        """Bearish: swing[2] high >= swing[0] high -> INVALIDATED."""
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=52000.0, index=10, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=49000.0, index=20, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=52500.0, index=30, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=48000.0, index=40, type=SwingType.LOW, timestamp=BASE),
            ),
        )
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bearish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_bearish_lower_low_not_lower_invalidated(self) -> None:
        """Bearish: swing[3] low >= swing[1] low -> INVALIDATED."""
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=52000.0, index=10, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=49000.0, index=20, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=51000.0, index=30, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=49500.0, index=40, type=SwingType.LOW, timestamp=BASE),
            ),
        )
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bearish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_all_same_type_swings_invalidated(self) -> None:
        """All HIGH swings -> INVALIDATED (not alternating)."""
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=100.0, index=5, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=110.0, index=10, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=120.0, index=15, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=130.0, index=20, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        store = _make_store(_flat_candles())
        view = MarketView(store, cursor=49, window_size=50)
        detector = FourSwingPullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_linearity_swings_outside_view_skipped(self) -> None:
        """Swing indices beyond the view range hit the bounds-check continue (line 248).

        The last swing pair (index 30→9999) is out of bounds and gets skipped.
        The other pairs are within view and linear, so linearity is 0.
        The pattern is valid (HL/HH/HL/HH), so status is DETECTED.
        The key assertion is that analysis completes without error.
        """
        candles = _bullish_linear_candles()
        store = _make_store(candles)
        n = len(candles)
        view = MarketView(store, cursor=n - 1, window_size=n)
        detector = FourSwingPullbackDetector()
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=48200.0, index=10, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=51500.0, index=20, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=49100.0, index=30, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=52800.0, index=9999, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.deviation_pct == 0.0

    def test_linearity_same_index_swings_skipped(self) -> None:
        """Two swings at same index hit idx1 == idx2 continue (line 250)."""
        candles = _bullish_linear_candles()
        store = _make_store(candles)
        n = len(candles)
        view = MarketView(store, cursor=n - 1, window_size=n)
        detector = FourSwingPullbackDetector()
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=48200.0, index=10, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=51500.0, index=10, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=49100.0, index=30, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=52800.0, index=40, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_linearity_flat_candles_between_swings_skipped(self) -> None:
        """Flat candles (high==low) between swings hit candle_range<=0 continue (line 259)."""
        flat_candle_data: list[CandleTuple] = []
        for i in range(41):
            flat_candle_data.append((100.0, 100.0, 100.0, 100.0, 1000.0))
        store = _make_store(flat_candle_data)
        view = MarketView(store, cursor=40, window_size=41)
        detector = FourSwingPullbackDetector()
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=100.0, index=5, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=100.0, index=15, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=100.0, index=25, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=100.0, index=35, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(1.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.INVALIDATED

    def test_confirmation_flat_candle_body_pct_zero(self) -> None:
        """Current candle with high==low yields body_pct=0 via _candle_body_pct (line 311).

        The last candle is flat (high==low), so _candle_body_pct returns 0.
        With min_body_pct=0.6, body_ok=False so the pattern stays DETECTED.
        """
        base_candles = _bullish_linear_candles()
        confirmation = [
            (53000.0, 53100.0, 52900.0, 53050.0, 1500.0),
            (53050.0, 53050.0, 53050.0, 53050.0, 1500.0),
        ]
        candles_data = base_candles + confirmation
        store = _make_store(candles_data)
        view = MarketView(store, cursor=len(candles_data) - 1, window_size=len(candles_data))
        detector = FourSwingPullbackDetector(
            confirmation_min_body_pct=0.6,
            confirmation_min_volume_ratio=0.0,
        )
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_4swing_fact(), _bullish_trend_fact(), _atr_fact(50.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED

    def test_volume_ratio_short_data_returns_one(self) -> None:
        """View with < 21 candles hits early return in _volume_ratio (line 317).

        Build a small dataset with linear candles matching the swing prices.
        With < 21 candles, _volume_ratio returns 1.0 (denominator guard).
        """
        linear_candles = _linear_candles_between(
            [(100.0, 2), (104.0, 4), (101.0, 6), (105.0, 8)],
            candle_range=2.0,
        )
        store = _make_store(linear_candles)
        view = MarketView(store, cursor=len(linear_candles) - 1, window_size=len(linear_candles))
        detector = FourSwingPullbackDetector(
            confirmation_min_body_pct=0.0,
            confirmation_min_volume_ratio=0.0,
        )
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=100.0, index=2, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=104.0, index=4, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=101.0, index=6, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=105.0, index=8, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(1.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED

    def test_volume_ratio_zero_avg_volume_returns_one(self) -> None:
        """All lookback volumes zero hits avg_vol<=0 branch in _volume_ratio (line 321).

        Build 25+ candles with zero volume. Swings are positioned within the range.
        Linear candles match swing prices so linearity passes. avg_vol=0 -> returns 1.0.
        """
        linear_candles = _linear_candles_between(
            [(100.0, 2), (104.0, 8), (101.0, 14), (105.0, 20)],
            candle_range=2.0,
        )
        zero_vol_candles = [(o, h, lo, c, 0.0) for o, h, lo, c, _v in linear_candles]
        store = _make_store(zero_vol_candles)
        view = MarketView(
            store, cursor=len(zero_vol_candles) - 1, window_size=len(zero_vol_candles)
        )
        detector = FourSwingPullbackDetector(
            confirmation_min_body_pct=0.0,
            confirmation_min_volume_ratio=0.0,
        )
        swing_fact = SwingFact(
            timestamp=BASE,
            evidence=(),
            swings=(
                SwingPoint(price=100.0, index=2, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=104.0, index=8, type=SwingType.HIGH, timestamp=BASE),
                SwingPoint(price=101.0, index=14, type=SwingType.LOW, timestamp=BASE),
                SwingPoint(price=105.0, index=20, type=SwingType.HIGH, timestamp=BASE),
            ),
        )
        result = detector.analyze(
            view,
            _keyed_facts(swing_fact, _bullish_trend_fact(), _atr_fact(1.0)),
        )
        fact = cast(PullbackFact, result.facts[0])
        assert fact.status == PullbackStatus.DETECTED
