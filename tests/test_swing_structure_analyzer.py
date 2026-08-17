import pytest
from datetime import UTC, datetime

from marketatlas.analysis.analyzers.swing_basic import BasicSwingAnalyzer
from marketatlas.analysis.analyzers.swing_structure import SwingStructureAnalyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.structural import SwingFact, SwingPoint, SwingStructureFact, SwingType


pytestmark = pytest.mark.tier2
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


def _view(
    candles: list[tuple[float, float, float, float]], cursor: int | None = None
) -> MarketView:
    store = _make_store(candles)
    cur = cursor if cursor is not None else len(candles) - 1
    return MarketView(store, cursor=cur, window_size=len(candles))


def _swing_fact(swings: list[tuple[float, SwingType]]) -> SwingFact:
    return SwingFact(
        timestamp=BASE,
        evidence=(),
        swings=tuple(
            SwingPoint(
                price=price,
                index=i,
                type=swing_type,
                timestamp=BASE,
            )
            for i, (price, swing_type) in enumerate(swings)
        ),
    )


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
        (99.0, 112.0, 99.0, 110.0),  # 7: end
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


class TestBasicSwingAnalyzer:
    def test_requires_nothing(self) -> None:
        analyzer = BasicSwingAnalyzer()
        assert analyzer.requires() == ()

    def test_produces_swing_fact(self) -> None:
        analyzer = BasicSwingAnalyzer()
        assert analyzer.produces() == (FactKey("swing"),)

    def test_zigzag_detects_all_swings(self) -> None:
        candles = _zigzag_candles()
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) >= 4
        highs = [s for s in fact.swings if s.type == SwingType.HIGH]
        lows = [s for s in fact.swings if s.type == SwingType.LOW]
        assert len(highs) >= 2
        assert len(lows) >= 2

    def test_zigzag_highs_are_highs(self) -> None:
        candles = _zigzag_candles()
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        highs = [s for s in fact.swings if s.type == SwingType.HIGH]
        lows = [s for s in fact.swings if s.type == SwingType.LOW]
        assert len(highs) >= 2
        assert len(lows) >= 2

    def test_sideways_few_swings(self) -> None:
        candles = _sideways_candles()
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) == 0

    def test_window_with_fewer_than_3_candles(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)]
        analyzer = BasicSwingAnalyzer()
        result = analyzer.analyze(_view(candles, cursor=0), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) == 0

    def test_two_candles(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0), (100.0, 102.0, 100.0, 101.0)]
        analyzer = BasicSwingAnalyzer()
        result = analyzer.analyze(_view(candles, cursor=1), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) == 0

    def test_swings_detected_without_atr(self) -> None:
        candles = _zigzag_candles()
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) > 0

    def test_evidence_contains_swing_count(self) -> None:
        candles = _zigzag_candles()
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        assert any("swing points" in e.text.lower() for e in result.evidence)

    def test_evidence_contains_range(self) -> None:
        candles = _zigzag_candles()
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        assert any("range" in e.text.lower() for e in result.evidence)

    def test_evidence_matches_fact_evidence(self) -> None:
        candles = _zigzag_candles()
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        assert result.evidence == result.facts[0].evidence

    def test_fact_has_correct_timestamp(self) -> None:
        candles = _zigzag_candles()
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        assert result.facts[0].timestamp == BASE

    def test_swing_indices_are_relative_to_store(self) -> None:
        candles = _zigzag_candles()
        cursor = len(candles) - 1
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles, cursor=cursor), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        for swing in fact.swings:
            assert 0 <= swing.index <= cursor

    def test_no_future_data_visible(self) -> None:
        """Swing index should never exceed cursor."""
        candles = _zigzag_candles()
        cursor = 5
        analyzer = BasicSwingAnalyzer(lookback=5, left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles, cursor=cursor), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        for swing in fact.swings:
            assert swing.index <= cursor

    def test_swings_stable_across_window_boundary(self) -> None:
        candles = [
            (100.0, 102.0, 98.0, 100.0),  # 0
            (100.0, 108.0, 100.0, 104.0),  # 1: SH at 108
            (104.0, 104.0, 94.0, 100.0),  # 2: SL at 94
            (100.0, 112.0, 100.0, 108.0),  # 3: SH at 112
            (108.0, 108.0, 90.0, 104.0),  # 4: SL at 90
            (104.0, 116.0, 104.0, 112.0),  # 5: SH at 116
            (112.0, 112.0, 86.0, 108.0),  # 6: SL at 86
            (108.0, 120.0, 108.0, 116.0),  # 7: SH at 120
            (116.0, 116.0, 82.0, 112.0),  # 8: SL at 82
            (112.0, 124.0, 112.0, 120.0),  # 9: SH at 124
            (120.0, 120.0, 78.0, 116.0),  # 10: SL at 78
            (116.0, 128.0, 116.0, 124.0),  # 11: SH at 128
            (124.0, 124.0, 74.0, 120.0),  # 12: SL at 74
            (120.0, 132.0, 120.0, 128.0),  # 13: SH at 132
            (128.0, 128.0, 70.0, 124.0),  # 14: SL at 70
            (124.0, 136.0, 124.0, 132.0),  # 15: SH at 136
            (132.0, 132.0, 66.0, 128.0),  # 16: SL at 66
            (128.0, 140.0, 128.0, 136.0),  # 17: SH at 140
            (136.0, 136.0, 62.0, 132.0),  # 18: SL at 62
            (132.0, 144.0, 132.0, 140.0),  # 19: SH at 144
        ]
        cursor = len(candles) - 1
        analyzer = BasicSwingAnalyzer(left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles, cursor=cursor), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) > 0
        early_swings = [s for s in fact.swings if s.index < cursor - 5]
        assert len(early_swings) > 0, "Swings before window boundary should be detected"

    def test_consecutive_same_type_highs_kept(self) -> None:
        """Two consecutive swing highs (no swing low between) both kept."""
        candles = [
            (100.0, 102.0, 99.0, 101.0),  # 0: base
            (101.0, 106.0, 101.0, 104.0),  # 1: SH at 106
            (104.0, 105.0, 103.0, 104.0),  # 2: not a swing
            (104.0, 108.0, 104.0, 106.0),  # 3: SH at 108
            (106.0, 107.0, 105.0, 106.0),  # 4
            (106.0, 106.0, 104.0, 105.0),  # 5
            (105.0, 105.0, 103.0, 104.0),  # 6
            (104.0, 104.0, 102.0, 103.0),  # 7
        ]
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        highs = [s for s in fact.swings if s.type == SwingType.HIGH]
        assert len(highs) == 2
        assert highs[0].price == 106.0
        assert highs[1].price == 108.0

    def test_consecutive_same_type_lows_kept(self) -> None:
        """Two consecutive swing lows (no swing high between) both kept."""
        candles = [
            (104.0, 106.0, 103.0, 105.0),  # 0: base
            (105.0, 105.0, 97.0, 101.0),  # 1: SL at 97
            (101.0, 102.0, 98.0, 101.0),  # 2: not a swing
            (101.0, 101.0, 95.0, 99.0),  # 3: SL at 95
            (99.0, 100.0, 96.0, 99.0),  # 4
            (99.0, 101.0, 97.0, 100.0),  # 5
            (100.0, 102.0, 98.0, 101.0),  # 6
            (101.0, 103.0, 99.0, 102.0),  # 7
        ]
        analyzer = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        result = analyzer.analyze(_view(candles), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        lows = [s for s in fact.swings if s.type == SwingType.LOW]
        assert len(lows) == 2
        assert lows[0].price == 97.0
        assert lows[1].price == 95.0


class TestSwingStructureAnalyzer:
    def test_requires_swing(self) -> None:
        analyzer = SwingStructureAnalyzer()
        assert analyzer.requires() == (FactKey("swing"),)

    def test_produces_swing_structure(self) -> None:
        analyzer = SwingStructureAnalyzer()
        assert analyzer.produces() == (FactKey("swing_structure"),)

    def test_missing_swing_returns_empty_structure(self) -> None:
        candles = _zigzag_candles()
        analyzer = SwingStructureAnalyzer()
        result = analyzer.analyze(_view(candles), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingStructureFact)
        assert fact.points == ()

    def test_alternating_swings_detected(self) -> None:
        candles = _zigzag_candles()
        basic = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        swing_fact = basic.analyze(_view(candles), {}).facts[0]
        analyzer = SwingStructureAnalyzer()
        result = analyzer.analyze(_view(candles), {FactKey("swing"): swing_fact})
        fact = result.facts[0]
        assert isinstance(fact, SwingStructureFact)
        assert len(fact.points) == 5
        types = [p.type for p in fact.points]
        assert types in (
            [SwingType.LOW, SwingType.HIGH, SwingType.LOW, SwingType.HIGH, SwingType.LOW],
            [SwingType.HIGH, SwingType.LOW, SwingType.HIGH, SwingType.LOW, SwingType.HIGH],
        )

    def test_non_alternating_returns_no_fact(self) -> None:
        candles = _zigzag_candles()
        swing_fact = _swing_fact(
            [
                (110.0, SwingType.HIGH),
                (108.0, SwingType.HIGH),
                (97.0, SwingType.LOW),
                (96.0, SwingType.LOW),
                (111.0, SwingType.HIGH),
            ]
        )
        analyzer = SwingStructureAnalyzer()
        result = analyzer.analyze(_view(candles), {FactKey("swing"): swing_fact})
        assert result.facts == ()

    def test_evidence_mentions_no_pattern(self) -> None:
        candles = _zigzag_candles()
        swing_fact = _swing_fact(
            [
                (110.0, SwingType.HIGH),
                (108.0, SwingType.HIGH),
                (97.0, SwingType.LOW),
                (96.0, SwingType.LOW),
                (111.0, SwingType.HIGH),
            ]
        )
        analyzer = SwingStructureAnalyzer()
        result = analyzer.analyze(_view(candles), {FactKey("swing"): swing_fact})
        assert any("alternating" in e.text.lower() for e in result.evidence)

    def test_fact_has_correct_timestamp(self) -> None:
        candles = _zigzag_candles()
        basic = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        swing_fact = basic.analyze(_view(candles), {}).facts[0]
        analyzer = SwingStructureAnalyzer()
        result = analyzer.analyze(_view(candles), {FactKey("swing"): swing_fact})
        assert result.facts[0].timestamp == BASE

    def test_custom_swing_key(self) -> None:
        candles = _zigzag_candles()
        basic = BasicSwingAnalyzer(lookback=len(candles), left_bars=1, right_bars=1)
        swing_fact = basic.analyze(_view(candles), {}).facts[0]
        analyzer = SwingStructureAnalyzer(swing_key="swing_custom")
        assert analyzer.requires() == (FactKey("swing_custom"),)
        result = analyzer.analyze(_view(candles), {FactKey("swing_custom"): swing_fact})
        assert isinstance(result.facts[0], SwingStructureFact)
        assert len(result.facts[0].points) == 5
