from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.analysis.analyzers.atr import ATRAnalyzer
from marketatlas.analysis.analyzers.atr_series import ATRSeriesAnalyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.primitive import ATRFact, ATRSeriesFact

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _make_store(highs: list[float], lows: list[float], closes: list[float]) -> MarketStore:
    candles = tuple(
        Candle(
            timestamp=BASE + timedelta(days=i),
            open=c,
            high=h,
            low=lo,
            close=c,
            volume=1000.0,
        )
        for i, (h, lo, c) in enumerate(zip(highs, lows, closes))
    )
    data = MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
    return MarketStore(data)


def _make_uniform_store(closes: list[float], spread: float = 1.0) -> MarketStore:
    return _make_store(
        highs=[c + spread for c in closes],
        lows=[c - spread for c in closes],
        closes=closes,
    )


def _analyze_at(store: MarketStore, cursor: int, period: int = 14) -> ATRSeriesFact:
    view = MarketView(store, cursor=cursor, window_size=cursor)
    result = ATRSeriesAnalyzer(period).analyze(view, {})
    fact = result.facts[0]
    assert isinstance(fact, ATRSeriesFact)
    return fact


class TestATRSeriesAnalyzer:
    def test_requires_empty(self) -> None:
        assert ATRSeriesAnalyzer(14).requires() == ()

    def test_produces_series_fact(self) -> None:
        assert ATRSeriesAnalyzer(14).produces() == (FactKey("atr_14_series"),)

    def test_single_candle_no_points(self) -> None:
        store = _make_store([105.0], [95.0], [100.0])
        fact = _analyze_at(store, 0)
        assert fact.points == ()

    def test_known_series_values(self) -> None:
        highs = [48.70, 48.72, 48.90, 48.87, 48.82]
        lows = [47.79, 48.14, 48.39, 48.37, 48.24]
        closes = [48.16, 48.61, 48.75, 48.63, 48.74]
        store = _make_store(highs, lows, closes)
        fact = _analyze_at(store, 4, period=3)
        assert fact.period == 3
        assert len(fact.points) == 4
        assert fact.points[-1].value == pytest.approx(0.5467, abs=0.01)

    def test_series_matches_scalar_atr_at_each_prefix(self) -> None:
        """Each series value equals what ATRAnalyzer reports at that cursor."""
        highs = [48.70, 48.72, 48.90, 48.87, 48.82, 48.75, 48.60, 48.90]
        lows = [47.79, 48.14, 48.39, 48.37, 48.24, 48.10, 48.00, 48.30]
        closes = [48.16, 48.61, 48.75, 48.63, 48.74, 48.70, 48.55, 48.80]
        store = _make_store(highs, lows, closes)
        period = 3
        series = _analyze_at(store, 7, period=period).points
        for i, point in enumerate(series):
            view = MarketView(store, cursor=i + 1, window_size=i + 1)
            scalar_fact = ATRAnalyzer(period).analyze(view, {}).facts[0]
            assert isinstance(scalar_fact, ATRFact)
            assert point.value == pytest.approx(scalar_fact.value, abs=1e-9)

    def test_final_value_matches_scalar_at_same_cursor(self) -> None:
        closes = [100.0 + i for i in range(20)]
        store = _make_uniform_store(closes, spread=2.0)
        series = _analyze_at(store, 19, period=5)
        view = MarketView(store, cursor=19, window_size=19)
        scalar_fact = ATRAnalyzer(5).analyze(view, {}).facts[0]
        assert isinstance(scalar_fact, ATRFact)
        assert series.points[-1].value == pytest.approx(scalar_fact.value)
        assert series.points[-1].value == pytest.approx(4.0)

    def test_series_is_causal_and_stable(self) -> None:
        """Values published at a timestamp never change as the cursor advances."""
        closes = [100.0 + i * 0.5 for i in range(50)]
        store = _make_uniform_store(closes, spread=2.0)
        early = _analyze_at(store, 30, period=14)
        later = _analyze_at(store, 49, period=14)
        early_by_ts = {p.timestamp: p.value for p in early.points}
        for point in later.points:
            if point.timestamp in early_by_ts:
                assert point.value == pytest.approx(early_by_ts[point.timestamp])

    def test_points_carry_candle_timestamps(self) -> None:
        closes = [100.0] * 5
        store = _make_uniform_store(closes, spread=1.0)
        fact = _analyze_at(store, 4, period=3)
        assert [p.timestamp for p in fact.points] == [
            BASE + timedelta(days=1 + i) for i in range(4)
        ]

    def test_period_larger_than_data(self) -> None:
        closes = [100.0, 101.0, 102.0]
        store = _make_uniform_store(closes, spread=1.0)
        fact = _analyze_at(store, 2, period=14)
        assert len(fact.points) == 2
        assert fact.points[-1].value == pytest.approx(2.0)

    def test_evidence_non_empty(self) -> None:
        closes = [100.0] * 20
        store = _make_uniform_store(closes)
        result = ATRSeriesAnalyzer(14).analyze(
            MarketView(store, cursor=19, window_size=19), {}
        )
        assert len(result.evidence) > 0
        assert result.evidence == result.facts[0].evidence
