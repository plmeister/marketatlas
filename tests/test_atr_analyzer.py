from datetime import UTC, datetime

import pytest

from marketatlas.analysis.analyzers.atr import ATRAnalyzer
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
        assert ATRAnalyzer(14).produces() == (ATRFact,)

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
        # TR[1] = max(106-94, |106-100|, |94-100|) = max(12, 6, 6) = 12
        # ATR = 12.0 (only 1 true range)
        assert result.facts[0].value == pytest.approx(12.0)

    def test_known_atr_values(self) -> None:
        highs = [48.70, 48.72, 48.90, 48.87, 48.82]
        lows = [47.79, 48.14, 48.39, 48.37, 48.24]
        closes = [48.16, 48.61, 48.75, 48.63, 48.74]
        store = _make_store(highs, lows, closes)
        view = MarketView(store, cursor=4, window_size=4)
        result = ATRAnalyzer(3).analyze(view, {})
        # TR[1] = max(48.72-48.14, |48.72-48.16|, |48.14-48.16|) = max(0.58, 0.56, 0.02) = 0.58
        # TR[2] = max(48.90-48.39, |48.90-48.61|, |48.39-48.61|) = max(0.51, 0.29, 0.22) = 0.51
        # TR[3] = max(48.87-48.37, |48.87-48.75|, |48.37-48.75|) = max(0.50, 0.12, 0.38) = 0.50
        # TR[4] = max(48.82-48.24, |48.82-48.63|, |48.24-48.63|) = max(0.58, 0.19, 0.39) = 0.58
        # ATR(3): SMA seed = (0.51+0.50+0.58)/3 = 0.53
        # Wilder: 0.53*(2/3) + 0.58*(1/3) ≈ 0.5467
        assert result.facts[0].value == pytest.approx(0.5467, abs=0.01)

    def test_wilder_smoothing(self) -> None:
        closes = [100.0 + i for i in range(20)]
        store = _make_uniform_store(closes, spread=2.0)
        view = MarketView(store, cursor=19, window_size=19)
        result = ATRAnalyzer(5).analyze(view, {})
        # All candles have same structure: high=close+2, low=close-2
        # TR for uniform candles = 4.0 (high-low)
        # After SMA seed, Wilder smoothing: ATR = prev * (period-1)/period + TR / period
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
        assert any("% of price" in e for e in result.evidence)

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
        # Different periods should produce different ATR values
        # (unless all TRs are identical)
        assert atr7.facts[0].period == 7
        assert atr21.facts[0].period == 21

    def test_evidence_matches_fact_evidence(self) -> None:
        closes = [100.0] * 20
        store = _make_uniform_store(closes)
        view = MarketView(store, cursor=19, window_size=19)
        result = ATRAnalyzer(14).analyze(view, {})
        assert result.evidence == result.facts[0].evidence
