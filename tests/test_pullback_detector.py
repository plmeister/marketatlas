from datetime import UTC, datetime

from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.patterns.pullback import PullbackDetector
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.pattern import PullbackFact, PullbackStatus
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import TrendDirection, TrendFact

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _make_store(candles_data: list[tuple[float, float, float, float]]) -> MarketStore:
    candles = tuple(
        Candle(
            timestamp=BASE,
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=1000.0,
        )
        for o, h, lo, c in candles_data
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


def _keyed_facts(
    trend: TrendFact, atr: ATRFact
) -> dict[FactKey, object]:
    return {
        FactKey("trend"): trend,
        FactKey("atr_14"): atr,
    }


def _rising_then_retracing_candles() -> list[tuple[float, float, float, float]]:
    """Bullish trend: rise from 100 to 110, retrace to 107 (1.5 ATR with ATR=2)."""
    return [
        (100, 101, 99, 100),
        (100, 102, 100, 101),
        (101, 103, 101, 102),
        (102, 104, 102, 103),
        (103, 105, 103, 104),
        (104, 106, 104, 105),
        (105, 107, 105, 106),
        (106, 108, 106, 107),
        (107, 109, 107, 108),
        (108, 110, 108, 109),  # swing high at 110
        (109, 109.5, 107.5, 108),  # start retracing
        (108, 108.5, 107, 107.5),
        (107.5, 107.8, 106.5, 107),  # retrace to 107 (1.5 ATR)
    ]


def _falling_then_retracing_candles() -> list[tuple[float, float, float, float]]:
    """Bearish trend: fall from 200 to 190, retrace up to 193 (1.5 ATR with ATR=2)."""
    return [
        (200, 201, 199, 200),
        (200, 200, 198, 199),
        (199, 199, 197, 198),
        (198, 198, 196, 197),
        (197, 197, 195, 196),
        (196, 196, 194, 195),
        (195, 195, 193, 194),
        (194, 194, 192, 193),
        (193, 193, 191, 192),
        (192, 192, 190, 191),  # swing low at 190
        (191, 192.5, 191, 192),  # start retracing
        (192, 193.5, 192, 193),
        (193, 194, 192.5, 193),  # retrace to 193 (1.5 ATR)
    ]


def _shallow_retrace_candles() -> list[tuple[float, float, float, float]]:
    """Bullish trend: rise from 100 to 110, very shallow retrace to 109.5."""
    return [
        (100, 101, 99, 100),
        (100, 102, 100, 101),
        (101, 103, 101, 102),
        (102, 104, 102, 103),
        (103, 105, 103, 104),
        (104, 106, 104, 105),
        (105, 107, 105, 106),
        (106, 108, 106, 107),
        (107, 109, 107, 108),
        (108, 110, 108, 109),  # swing high at 110
        (109, 109.8, 109, 109.5),  # very shallow retrace
    ]


def _deep_retrace_candles() -> list[tuple[float, float, float, float]]:
    """Bullish trend: rise from 100 to 110, deep retrace past 108."""
    return [
        (100, 101, 99, 100),
        (100, 102, 100, 101),
        (101, 103, 101, 102),
        (102, 104, 102, 103),
        (103, 105, 103, 104),
        (104, 106, 104, 105),
        (105, 107, 105, 106),
        (106, 108, 106, 107),
        (107, 109, 107, 108),
        (108, 110, 108, 109),  # swing high at 110
        (109, 109, 105, 106),  # deep retrace to 106
        (106, 106, 103, 104),  # even deeper
    ]


class TestPullbackDetector:
    def test_requires_trend_and_atr(self) -> None:
        detector = PullbackDetector()
        assert detector.requires() == (FactKey("trend"), FactKey("atr_14"))

    def test_produces_pullback_fact(self) -> None:
        detector = PullbackDetector()
        assert detector.produces() == (FactKey("pullback"),)

    def test_bullish_trend_detected_pullback(self) -> None:
        candles = _rising_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.status == PullbackStatus.DETECTED
        assert fact.direction == TrendDirection.BULLISH
        assert fact.retracement_atr > 0

    def test_bearish_trend_detected_pullback(self) -> None:
        candles = _falling_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bearish_trend_fact(), _atr_fact(2.0)),
        )
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.status == PullbackStatus.DETECTED
        assert fact.direction == TrendDirection.BEARISH
        assert fact.retracement_atr > 0

    def test_shallow_retrace_below_threshold(self) -> None:
        candles = _shallow_retrace_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.status == PullbackStatus.INVALIDATED

    def test_deep_retrace_invalidated(self) -> None:
        candles = _deep_retrace_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.status == PullbackStatus.INVALIDATED

    def test_neutral_trend_no_pullback(self) -> None:
        candles = _rising_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector()
        neutral_trend = TrendFact(
            timestamp=BASE,
            evidence=(),
            direction=TrendDirection.NEUTRAL,
            strength=0.0,
        )
        result = detector.analyze(
            view,
            _keyed_facts(neutral_trend, _atr_fact(2.0)),
        )
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.status == PullbackStatus.INVALIDATED
        assert fact.retracement_atr == 0.0

    def test_zero_atr_no_pullback(self) -> None:
        candles = _rising_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(0.0)),
        )
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.status == PullbackStatus.INVALIDATED

    def test_evidence_contains_pullback_status(self) -> None:
        candles = _rising_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        assert any("detected" in e.text.lower() for e in result.evidence)

    def test_evidence_contains_retracement_atr(self) -> None:
        candles = _rising_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        assert any("atr" in e.text.lower() for e in result.evidence)

    def test_evidence_contains_price_info(self) -> None:
        candles = _rising_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        assert any("current price" in e.text.lower() for e in result.evidence)

    def test_fact_has_correct_timestamp(self) -> None:
        candles = _rising_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        assert result.facts[0].timestamp == BASE

    def test_custom_thresholds(self) -> None:
        candles = _shallow_retrace_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.1, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.status == PullbackStatus.DETECTED

    def test_retracement_atr_is_positive(self) -> None:
        candles = _rising_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.retracement_atr > 0

    def test_no_swing_points(self) -> None:
        flat_candles = [(100.0, 100.0, 100.0, 100.0)] * 5
        store = _make_store(flat_candles)
        view = MarketView(store, cursor=len(flat_candles) - 1, window_size=len(flat_candles) - 1)
        detector = PullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.status == PullbackStatus.INVALIDATED

    def test_evidence_matches_fact_evidence(self) -> None:
        candles = _rising_then_retracing_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        detector = PullbackDetector(min_retracement_atr=0.5, max_retracement_atr=2.0)
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        assert result.evidence == result.facts[0].evidence

    def test_short_data_handled(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0), (100.0, 102.0, 100.0, 101.0)]
        store = _make_store(candles)
        view = MarketView(store, cursor=1, window_size=1)
        detector = PullbackDetector()
        result = detector.analyze(
            view,
            _keyed_facts(_bullish_trend_fact(), _atr_fact(2.0)),
        )
        assert isinstance(result.facts[0], PullbackFact)
