from datetime import UTC, datetime

import pytest
from marketatlas.analysis.analyzers.atr import ATRAnalyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.primitive import ATRFact

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _make_store(
    highs: list[float], lows: list[float], closes: list[float]
) -> MarketStore:
    candles = tuple(
        Candle(
            timestamp=BASE,
            open=c,
            high=h,
            low=lo,
            close=c,
            volume=1000.0,
        )
        for h, lo, c in zip(highs, lows, closes)
    )
    data = MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
    return MarketStore(data)


def _make_uniform_store(closes: list[float], spread: float = 1.0) -> MarketStore:
    return _make_store(
        highs=[c + spread for c in closes],
        lows=[c - spread for c in closes],
        closes=closes,
    )


class TestATRAnalyzer:
    def test_requires_empty(self) -> None:
        assert ATRAnalyzer(14).requires() == ()

    def test_produces_atr_fact(self) -> None:
        assert ATRAnalyzer(14).produces() == (FactKey("atr_14"),)

    def test_single_candle(self) -> None:
        store = _make_store([105.0], [95.0], [100.0])
        view = MarketView(store, cursor=0, window_size=0)
        result = ATRAnalyzer(14).analyze(view, {})
        assert len(result.facts) == 1
        assert isinstance(result.facts[0], ATRFact)
        assert result.facts[0].value == pytest.approx(10.0)

    def test_two_candles_same_close(self) -> None:
        store = _make_store([105.0, 106.0], [95.0, 94.0], [100.0, 100.0])
        view = MarketView(store, cursor=1, window_size=1)
        result = ATRAnalyzer(14).analyze(view, {})
        assert result.facts[0].value == pytest.approx(12.0)

    def test_known_atr_values(self) -> None:
        highs = [48.70, 48.72, 48.90, 48.87, 48.82]
        lows = [47.79, 48.14, 48.39, 48.37, 48.24]
        closes = [48.16, 48.61, 48.75, 48.63, 48.74]
        store = _make_store(highs, lows, closes)
        view = MarketView(store, cursor=4, window_size=4)
        result = ATRAnalyzer(3).analyze(view, {})
        assert result.facts[0].value == pytest.approx(0.5467, abs=0.01)

    def test_wilder_smoothing(self) -> None:
        closes = [100.0 + i for i in range(20)]
        store = _make_uniform_store(closes, spread=2.0)
        view = MarketView(store, cursor=19, window_size=19)
        result = ATRAnalyzer(5).analyze(view, {})
        assert result.facts[0].value == pytest.approx(4.0)

    def test_period_larger_than_data(self) -> None:
        closes = [100.0, 101.0, 102.0]
        store = _make_uniform_store(closes, spread=1.0)
        view = MarketView(store, cursor=2, window_size=2)
        result = ATRAnalyzer(14).analyze(view, {})
        assert result.facts[0].value > 0

    def test_atr_represents_pct_of_price(self) -> None:
        closes = [100.0] * 20
        store = _make_uniform_store(closes, spread=2.0)
        view = MarketView(store, cursor=19, window_size=19)
        result = ATRAnalyzer(14).analyze(view, {})
        assert any("% of price" in e.text for e in result.evidence)

    def test_evidence_non_empty(self) -> None:
        closes = [100.0] * 20
        store = _make_uniform_store(closes)
        view = MarketView(store, cursor=19, window_size=19)
        result = ATRAnalyzer(14).analyze(view, {})
        assert len(result.evidence) > 0

    def test_fact_has_correct_timestamp(self) -> None:
        closes = [100.0] * 20
        store = _make_uniform_store(closes)
        view = MarketView(store, cursor=19, window_size=19)
        result = ATRAnalyzer(14).analyze(view, {})
        assert result.facts[0].timestamp == BASE

    def test_different_periods(self) -> None:
        closes = [100.0 + i * 0.5 for i in range(50)]
        store = _make_uniform_store(closes, spread=2.0)
        view = MarketView(store, cursor=49, window_size=49)
        atr7 = ATRAnalyzer(7).analyze(view, {})
        atr21 = ATRAnalyzer(21).analyze(view, {})
        assert atr7.facts[0].period == 7
        assert atr21.facts[0].period == 21

    def test_evidence_matches_fact_evidence(self) -> None:
        closes = [100.0] * 20
        store = _make_uniform_store(closes)
        view = MarketView(store, cursor=19, window_size=19)
        result = ATRAnalyzer(14).analyze(view, {})
        assert result.evidence == result.facts[0].evidence
