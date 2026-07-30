from datetime import UTC, datetime

from marketatlas.analysis.analyzers.swing import SwingStructureAnalyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import SwingFact, SwingType

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


def _keyed_facts(atr: ATRFact) -> dict[FactKey, Fact]:
    return {FactKey("atr_14"): atr}


def _zigzag_candles() -> list[tuple[float, float, float, float]]:
    """Clean zigzag: SH(106) SL(99) SH(108) SL(98) SH(110) SL(97)."""
    return [
        (100.0, 102.0, 98.0, 100.0),  # 0: base
        (100.0, 106.0, 100.0, 104.0),  # 1: SH at 106
        (104.0, 104.0, 99.0, 100.0),  # 2: SL at 99
        (100.0, 108.0, 100.0, 106.0),  # 3: SH at 108
        (106.0, 106.0, 98.0, 100.0),  # 4: SL at 98
        (100.0, 110.0, 100.0, 108.0),  # 5: SH at 110
        (108.0, 108.0, 97.0, 99.0),  # 6: SL at 97
        (99.0, 112.0, 99.0, 110.0),  # 7: end (no next candle for SH check)
    ]


def _sideways_candles() -> list[tuple[float, float, float, float]]:
    """Flat market: no clear swing points."""
    return [
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.0, 100.0),
    ]


def _close_swings_candles() -> list[tuple[float, float, float, float]]:
    """Two swing highs very close in price (within 0.3 ATR with ATR=2.0)."""
    return [
        (100.0, 102.0, 98.0, 100.0),  # 0: base
        (100.0, 105.0, 100.0, 103.0),  # 1: SH at 105
        (103.0, 103.0, 99.0, 100.0),  # 2: SL at 99
        (100.0, 105.4, 100.0, 103.0),  # 3: SH at 105.4 (close to 105)
        (103.0, 103.0, 98.5, 99.5),  # 4: SL at 98.5
        (99.5, 105.2, 99.5, 103.0),  # 5: SH at 105.2 (close to 105.4)
        (103.0, 103.0, 101.0, 102.0),
    ]


class TestSwingStructureAnalyzer:
    def test_requires_atr(self) -> None:
        analyzer = SwingStructureAnalyzer()
        assert analyzer.requires() == (FactKey("atr_14"),)

    def test_produces_swing_fact(self) -> None:
        analyzer = SwingStructureAnalyzer()
        assert analyzer.produces() == (FactKey("swing"),)

    def test_zigzag_alternating_pattern(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) >= 4
        for i in range(len(fact.swings) - 1):
            assert fact.swings[i].type != fact.swings[i + 1].type

    def test_zigzag_highs_are_highs(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        highs = [s for s in fact.swings if s.type == SwingType.HIGH]
        lows = [s for s in fact.swings if s.type == SwingType.LOW]
        assert len(highs) >= 2
        assert len(lows) >= 2

    def test_sideways_few_swings(self) -> None:
        candles = _sideways_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) == 0

    def test_filter_removes_close_swings(self) -> None:
        candles = _close_swings_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        highs = [s for s in fact.swings if s.type == SwingType.HIGH]
        assert len(highs) == 1

    def test_window_with_fewer_than_3_candles(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)]
        store = _make_store(candles)
        view = MarketView(store, cursor=0, window_size=1)
        analyzer = SwingStructureAnalyzer()
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) == 0

    def test_two_candles(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0), (100.0, 102.0, 100.0, 101.0)]
        store = _make_store(candles)
        view = MarketView(store, cursor=1, window_size=1)
        analyzer = SwingStructureAnalyzer()
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) == 0

    def test_zero_atr_returns_empty(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles))
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(0.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) == 0

    def test_missing_atr_returns_empty(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles))
        result = analyzer.analyze(view, {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) == 0

    def test_evidence_contains_swing_count(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        assert any("swing points" in e.text.lower() for e in result.evidence)

    def test_evidence_contains_range(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        assert any("range" in e.text.lower() for e in result.evidence)

    def test_evidence_matches_fact_evidence(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        assert result.evidence == result.facts[0].evidence

    def test_fact_has_correct_timestamp(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        assert result.facts[0].timestamp == BASE

    def test_swing_indices_are_relative_to_store(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        cursor = len(candles) - 1
        view = MarketView(store, cursor=cursor, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        for swing in fact.swings:
            assert 0 <= swing.index <= cursor

    def test_no_future_data_visible(self) -> None:
        """Swing index should never exceed cursor."""
        candles = _zigzag_candles()
        store = _make_store(candles)
        cursor = 5
        view = MarketView(store, cursor=cursor, window_size=5)
        analyzer = SwingStructureAnalyzer(lookback=5, min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        for swing in fact.swings:
            assert swing.index <= cursor

    def test_custom_lookback(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        cursor = len(candles) - 1
        view = MarketView(store, cursor=cursor, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=4, min_swing_atr=0.3)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        for swing in fact.swings:
            assert swing.index >= cursor - 4

    def test_custom_atr_key(self) -> None:
        candles = _zigzag_candles()
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(
            lookback=len(candles), min_swing_atr=0.3, atr_key="atr_custom"
        )
        facts = {FactKey("atr_custom"): _atr_fact(2.0)}
        result = analyzer.analyze(view, facts)
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) > 0

    def test_consecutive_same_type_high_replaced(self) -> None:
        """Two consecutive swing highs (no swing low between) where second is higher."""
        # SH at candle 1 (H=106), no swing low at candle 2, SH at candle 3 (H=108)
        # Candle 2 L=103 is NOT a swing low because 103 > c1.L=101
        candles = [
            (100.0, 102.0, 99.0, 101.0),  # 0: base
            (101.0, 106.0, 101.0, 104.0),  # 1: SH at 106 (106>102, 106>105)
            (104.0, 105.0, 103.0, 104.0),  # 2: not a swing (H=105<106, L=103>101)
            (104.0, 108.0, 104.0, 106.0),  # 3: SH at 108 (108>105, 108>107)
            (106.0, 107.0, 105.0, 106.0),  # 4
            (106.0, 106.0, 104.0, 105.0),  # 5
            (105.0, 105.0, 103.0, 104.0),  # 6
            (104.0, 104.0, 102.0, 103.0),  # 7
        ]
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.0)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        highs = [s for s in fact.swings if s.type == SwingType.HIGH]
        assert len(highs) == 1
        assert highs[0].price == 108.0

    def test_consecutive_same_type_low_replaced(self) -> None:
        """Two consecutive swing lows (no swing high between) where second is lower."""
        # SL at candle 1 (L=97), no swing high at candle 2, SL at candle 3 (L=95)
        candles = [
            (104.0, 106.0, 103.0, 105.0),  # 0: base
            (105.0, 105.0, 97.0, 101.0),  # 1: SL at 97 (97<103, 97<98)
            (101.0, 102.0, 98.0, 101.0),  # 2: not a swing (H=102<105, L=98>97)
            (101.0, 101.0, 95.0, 99.0),  # 3: SL at 95 (95<98, 95<96)
            (99.0, 100.0, 96.0, 99.0),  # 4
            (99.0, 101.0, 97.0, 100.0),  # 5
            (100.0, 102.0, 98.0, 101.0),  # 6
            (101.0, 103.0, 99.0, 102.0),  # 7
        ]
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.0)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        lows = [s for s in fact.swings if s.type == SwingType.LOW]
        assert len(lows) == 1
        assert lows[0].price == 95.0

    def test_consecutive_same_type_evidence_logged(self) -> None:
        """Evidence mentions consecutive same-type swing removal."""
        candles = [
            (100.0, 102.0, 99.0, 101.0),
            (101.0, 106.0, 101.0, 104.0),  # SH at 106
            (104.0, 105.0, 103.0, 104.0),  # no swing
            (104.0, 108.0, 104.0, 106.0),  # SH at 108
            (106.0, 107.0, 105.0, 106.0),
            (106.0, 106.0, 104.0, 105.0),
            (105.0, 105.0, 103.0, 104.0),
            (104.0, 104.0, 102.0, 103.0),
        ]
        store = _make_store(candles)
        view = MarketView(store, cursor=len(candles) - 1, window_size=len(candles) - 1)
        analyzer = SwingStructureAnalyzer(lookback=len(candles), min_swing_atr=0.0)
        result = analyzer.analyze(view, _keyed_facts(_atr_fact(2.0)))
        assert any("consecutive" in e.text.lower() for e in result.evidence)
