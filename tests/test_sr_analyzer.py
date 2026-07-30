from datetime import UTC, datetime

from marketatlas.analysis.analyzers.sr import SupportResistanceAnalyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import (
    SRFact,
    SwingFact,
    SwingPoint,
    SwingType,
)

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


def _make_swings(
    prices_and_types: list[tuple[float, SwingType]],
) -> tuple[SwingPoint, ...]:
    return tuple(
        SwingPoint(
            price=price,
            index=i,
            type=stype,
            timestamp=BASE,
        )
        for i, (price, stype) in enumerate(prices_and_types)
    )


def _keyed_facts(swings: SwingFact, atr: ATRFact) -> dict[FactKey, Fact]:
    return {FactKey("swing"): swings, FactKey("atr_14"): atr}


def _swings_fact(swings: tuple[SwingPoint, ...]) -> SwingFact:
    return SwingFact(timestamp=BASE, evidence=(), swings=swings)


class TestSupportResistanceAnalyzer:
    def test_requires(self) -> None:
        analyzer = SupportResistanceAnalyzer()
        reqs = analyzer.requires()
        assert FactKey("swing") in reqs
        assert FactKey("atr_14") in reqs

    def test_produces(self) -> None:
        analyzer = SupportResistanceAnalyzer()
        assert analyzer.produces() == (FactKey("sr"),)

    def test_no_swings_returns_empty(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer()
        sf = _swings_fact(())
        result = analyzer.analyze(view, _keyed_facts(sf, _atr_fact()))
        fact = result.facts[0]
        assert isinstance(fact, SRFact)
        assert len(fact.levels) == 0

    def test_no_atr_returns_empty(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer()
        sf = _swings_fact(_make_swings([(100.0, SwingType.HIGH), (90.0, SwingType.LOW)]))
        bad_atr = ATRFact(timestamp=BASE, evidence=(), value=0.0, period=14)
        result = analyzer.analyze(view, _keyed_facts(sf, bad_atr))
        fact = result.facts[0]
        assert isinstance(fact, SRFact)
        assert len(fact.levels) == 0

    def test_single_swing_strength_one(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer()
        sf = _swings_fact(_make_swings([(95.0, SwingType.LOW)]))
        result = analyzer.analyze(view, _keyed_facts(sf, _atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SRFact)
        assert len(fact.levels) == 1
        assert fact.levels[0].strength == 1
        assert fact.levels[0].type == "support"

    def test_clustered_swings_merge(self) -> None:
        """Swings within tolerance cluster into one level."""
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        # tolerance = 0.5 * ATR = 0.5 * 2.0 = 1.0
        # Two swings at 100.0 and 100.5 → within tolerance → cluster
        analyzer = SupportResistanceAnalyzer(level_tolerance_atr=0.5)
        sf = _swings_fact(
            _make_swings(
                [
                    (100.0, SwingType.HIGH),
                    (100.5, SwingType.HIGH),
                    (90.0, SwingType.LOW),
                ]
            )
        )
        result = analyzer.analyze(view, _keyed_facts(sf, _atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SRFact)
        # Two clusters: {100.0, 100.5} and {90.0}
        assert len(fact.levels) == 2
        clustered = [lv for lv in fact.levels if lv.strength == 2]
        assert len(clustered) == 1
        assert abs(clustered[0].price - 100.25) < 0.01

    def test_support_below_resistance_above(self) -> None:
        """Levels below current close are support, above are resistance."""
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        # current close = 100.0
        analyzer = SupportResistanceAnalyzer(level_tolerance_atr=0.5)
        sf = _swings_fact(
            _make_swings(
                [
                    (95.0, SwingType.LOW),
                    (105.0, SwingType.HIGH),
                ]
            )
        )
        result = analyzer.analyze(view, _keyed_facts(sf, _atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SRFact)
        support = [lv for lv in fact.levels if lv.type == "support"]
        resistance = [lv for lv in fact.levels if lv.type == "resistance"]
        assert len(support) == 1
        assert support[0].price == 95.0
        assert len(resistance) == 1
        assert resistance[0].price == 105.0

    def test_levels_sorted_by_price(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer(level_tolerance_atr=0.5)
        sf = _swings_fact(
            _make_swings(
                [
                    (110.0, SwingType.HIGH),
                    (80.0, SwingType.LOW),
                    (95.0, SwingType.LOW),
                    (105.0, SwingType.HIGH),
                ]
            )
        )
        result = analyzer.analyze(view, _keyed_facts(sf, _atr_fact(2.0)))
        fact = result.facts[0]
        assert isinstance(fact, SRFact)
        prices = [lv.price for lv in fact.levels]
        assert prices == sorted(prices)

    def test_evidence_mentions_level_count(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer(level_tolerance_atr=0.5)
        sf = _swings_fact(
            _make_swings(
                [
                    (95.0, SwingType.LOW),
                    (105.0, SwingType.HIGH),
                ]
            )
        )
        result = analyzer.analyze(view, _keyed_facts(sf, _atr_fact(2.0)))
        assert any("2 S/R levels" in e.text for e in result.evidence)

    def test_evidence_nearest_support(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer(level_tolerance_atr=0.5)
        sf = _swings_fact(
            _make_swings(
                [
                    (80.0, SwingType.LOW),
                    (95.0, SwingType.LOW),
                    (105.0, SwingType.HIGH),
                ]
            )
        )
        result = analyzer.analyze(view, _keyed_facts(sf, _atr_fact(2.0)))
        assert any("Nearest support" in e.text for e in result.evidence)

    def test_evidence_nearest_resistance(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer(level_tolerance_atr=0.5)
        sf = _swings_fact(
            _make_swings(
                [
                    (95.0, SwingType.LOW),
                    (105.0, SwingType.HIGH),
                    (115.0, SwingType.HIGH),
                ]
            )
        )
        result = analyzer.analyze(view, _keyed_facts(sf, _atr_fact(2.0)))
        assert any("Nearest resistance" in e.text for e in result.evidence)

    def test_fact_timestamp_matches_view(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer()
        sf = _swings_fact(_make_swings([(95.0, SwingType.LOW)]))
        result = analyzer.analyze(view, _keyed_facts(sf, _atr_fact(2.0)))
        assert result.facts[0].timestamp == BASE

    def test_custom_keys(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer(swing_key="swing_custom", atr_key="atr_custom")
        sf = _swings_fact(_make_swings([(95.0, SwingType.LOW)]))
        atr = _atr_fact(2.0)
        facts = {FactKey("swing_custom"): sf, FactKey("atr_custom"): atr}
        result = analyzer.analyze(view, facts)
        fact = result.facts[0]
        assert isinstance(fact, SRFact)
        assert len(fact.levels) == 1

    def test_missing_swing_fact(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer()
        result = analyzer.analyze(view, {})
        fact = result.facts[0]
        assert isinstance(fact, SRFact)
        assert len(fact.levels) == 0

    def test_missing_atr_fact(self) -> None:
        candles = [(100.0, 101.0, 99.0, 100.0)] * 5
        store = _make_store(candles)
        view = MarketView(store, cursor=4, window_size=4)
        analyzer = SupportResistanceAnalyzer()
        sf = _swings_fact(_make_swings([(95.0, SwingType.LOW)]))
        facts = {FactKey("swing"): sf}
        result = analyzer.analyze(view, facts)
        fact = result.facts[0]
        assert isinstance(fact, SRFact)
        assert len(fact.levels) == 0
