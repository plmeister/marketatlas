from datetime import UTC, datetime

import pytest
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.primitive import EMAFact

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _make_store(closes: list[float]) -> MarketStore:
    candles = tuple(
        Candle(
            timestamp=BASE,
            open=c,
            high=c + 1.0,
            low=c - 1.0,
            close=c,
            volume=1000.0,
        )
        for c in closes
    )
    data = MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
    return MarketStore(data)


class TestEMAAnalyzer:
    def test_requires_empty(self) -> None:
        assert EMAAnalyzer(20).requires() == ()

    def test_produces_ema_fact(self) -> None:
        assert EMAAnalyzer(20).produces() == ((EMAFact, "ema_20"),)

    def test_period_1_returns_current_price(self) -> None:
        closes = [100.0, 101.0, 102.0, 103.0, 104.0]
        store = _make_store(closes)
        view = MarketView(store, cursor=4, window_size=4)
        result = EMAAnalyzer(1).analyze(view, {})
        assert len(result.facts) == 1
        assert isinstance(result.facts[0], EMAFact)
        assert result.facts[0].value == pytest.approx(104.0)
        assert result.facts[0].period == 1

    def test_sma_seed(self) -> None:
        closes = [10.0, 20.0, 30.0, 40.0, 50.0]
        store = _make_store(closes)
        view = MarketView(store, cursor=4, window_size=4)
        result = EMAAnalyzer(3).analyze(view, {})
        assert result.facts[0].value == pytest.approx(40.0)

    def test_known_ema_values(self) -> None:
        closes = [22.27, 22.19, 22.08, 22.17, 22.18, 22.13, 22.23, 22.43, 22.24, 22.29]
        store = _make_store(closes)
        view = MarketView(store, cursor=len(closes) - 1, window_size=len(closes))
        result = EMAAnalyzer(10).analyze(view, {})
        expected_sma = sum(closes) / 10
        assert result.facts[0].value == pytest.approx(expected_sma)

    def test_period_larger_than_data(self) -> None:
        closes = [100.0, 200.0]
        store = _make_store(closes)
        view = MarketView(store, cursor=1, window_size=1)
        result = EMAAnalyzer(20).analyze(view, {})
        assert result.facts[0].value == pytest.approx(150.0)

    def test_evidence_non_empty(self) -> None:
        closes = [100.0] * 20
        store = _make_store(closes)
        view = MarketView(store, cursor=19, window_size=19)
        result = EMAAnalyzer(20).analyze(view, {})
        assert len(result.evidence) > 0

    def test_bullish_signal_when_ema_below_price(self) -> None:
        closes = [100.0 + i * 0.5 for i in range(25)]
        store = _make_store(closes)
        view = MarketView(store, cursor=24, window_size=24)
        result = EMAAnalyzer(20).analyze(view, {})
        assert any("bullish" in e.text.lower() for e in result.evidence)

    def test_bearish_signal_when_ema_above_price(self) -> None:
        closes = [200.0 - i * 0.5 for i in range(25)]
        store = _make_store(closes)
        view = MarketView(store, cursor=24, window_size=24)
        result = EMAAnalyzer(20).analyze(view, {})
        assert any("bearish" in e.text.lower() for e in result.facts[0].evidence)

    def test_fact_has_correct_timestamp(self) -> None:
        closes = [100.0] * 20
        store = _make_store(closes)
        view = MarketView(store, cursor=19, window_size=19)
        result = EMAAnalyzer(20).analyze(view, {})
        assert result.facts[0].timestamp == BASE

    def test_different_periods(self) -> None:
        closes = [100.0 + i for i in range(50)]
        store = _make_store(closes)
        view = MarketView(store, cursor=49, window_size=49)
        ema10 = EMAAnalyzer(10).analyze(view, {})
        ema30 = EMAAnalyzer(30).analyze(view, {})
        assert ema10.facts[0].value != ema30.facts[0].value

    def test_evidence_matches_fact_evidence(self) -> None:
        closes = [100.0] * 20
        store = _make_store(closes)
        view = MarketView(store, cursor=19, window_size=19)
        result = EMAAnalyzer(20).analyze(view, {})
        assert result.evidence == result.facts[0].evidence
