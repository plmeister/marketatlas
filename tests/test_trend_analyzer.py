from datetime import UTC, datetime

import pytest
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.analyzers.trend import TrendAnalyzer
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import TrendDirection, TrendFact

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


def _rising_closes(n: int, start: float = 100.0, step: float = 1.0) -> list[float]:
    return [start + i * step for i in range(n)]


def _falling_closes(n: int, start: float = 200.0, step: float = 1.0) -> list[float]:
    return [start - i * step for i in range(n)]


def _flat_closes(n: int, value: float = 100.0) -> list[float]:
    return [value] * n


def _make_ema_facts(
    view: MarketView, fast_period: int, slow_period: int
) -> dict[tuple[type, str], object]:
    fast = EMAAnalyzer(fast_period)
    slow = EMAAnalyzer(slow_period)
    fast_result = fast.analyze(view, {})
    slow_result = slow.analyze(view, {})
    return {
        (EMAFact, fast.instance_key): fast_result.facts[0],
        (EMAFact, slow.instance_key): slow_result.facts[0],
    }


def _trend(result: AnalysisResult) -> TrendFact:
    fact = result.facts[0]
    assert isinstance(fact, TrendFact)
    return fact


class TestTrendAnalyzer:
    def test_requires_empty(self) -> None:
        assert TrendAnalyzer().requires() == (
            (EMAFact, "ema_20"),
            (EMAFact, "ema_50"),
        )

    def test_produces_trend_fact(self) -> None:
        assert TrendAnalyzer().produces() == ((TrendFact, "trend"),)

    def test_bullish_when_fast_above_slow(self) -> None:
        closes = _rising_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)
        result = TrendAnalyzer().analyze(view, facts)
        assert len(result.facts) == 1
        trend = _trend(result)
        assert trend.direction == TrendDirection.BULLISH

    def test_bearish_when_fast_below_slow(self) -> None:
        closes = _falling_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)
        result = TrendAnalyzer().analyze(view, facts)
        trend = _trend(result)
        assert trend.direction == TrendDirection.BEARISH

    def test_neutral_when_emas_equal(self) -> None:
        closes = _flat_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)
        result = TrendAnalyzer().analyze(view, facts)
        trend = _trend(result)
        assert trend.direction == TrendDirection.NEUTRAL
        assert trend.strength == pytest.approx(0.0)

    def test_strength_scales_with_spread(self) -> None:
        steep_rise = [100.0 + i * 5.0 for i in range(60)]
        gentle_rise = [100.0 + i * 0.5 for i in range(60)]

        store_steep = _make_store(steep_rise)
        view_steep = MarketView(store_steep, cursor=59, window_size=59)
        facts_steep = _make_ema_facts(view_steep, 20, 50)
        result_steep = TrendAnalyzer().analyze(view_steep, facts_steep)

        store_gentle = _make_store(gentle_rise)
        view_gentle = MarketView(store_gentle, cursor=59, window_size=59)
        facts_gentle = _make_ema_facts(view_gentle, 20, 50)
        result_gentle = TrendAnalyzer().analyze(view_gentle, facts_gentle)

        assert _trend(result_steep).strength > _trend(result_gentle).strength

    def test_strength_uses_atr_when_available(self) -> None:
        closes = _rising_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)

        analyzer = TrendAnalyzer()
        result_no_atr = analyzer.analyze(view, facts)

        facts_with_atr: dict = {
            **facts,
            (ATRFact, "atr_14"): ATRFact(
                timestamp=BASE,
                evidence=(
                    EvidenceEntry(
                        text="ATR14 = 2.0",
                        level=EvidenceLevel.INFO,
                        source="ATRAnalyzer",
                    ),
                ),
                value=2.0,
                period=14,
            ),
        }
        result_with_atr = analyzer.analyze(view, facts_with_atr)

        assert _trend(result_with_atr).strength != _trend(result_no_atr).strength

    def test_evidence_contains_trend_direction(self) -> None:
        closes = _rising_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)
        result = TrendAnalyzer().analyze(view, facts)
        assert any("bullish" in e.text.lower() for e in result.evidence)

    def test_evidence_contains_strength(self) -> None:
        closes = _rising_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)
        result = TrendAnalyzer().analyze(view, facts)
        assert any("strength" in e.text.lower() for e in result.evidence)

    def test_evidence_confirms_price_position(self) -> None:
        closes = _rising_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)
        result = TrendAnalyzer().analyze(view, facts)
        assert any("price above both emas" in e.text.lower() for e in result.evidence)

    def test_fact_has_correct_timestamp(self) -> None:
        closes = _rising_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)
        result = TrendAnalyzer().analyze(view, facts)
        assert result.facts[0].timestamp == BASE

    def test_short_data_handled(self) -> None:
        closes = [100.0, 101.0, 102.0]
        store = _make_store(closes)
        view = MarketView(store, cursor=2, window_size=2)
        facts = _make_ema_facts(view, 2, 3)
        result = TrendAnalyzer(
            fast_key="ema_2", slow_key="ema_3"
        ).analyze(view, facts)
        assert isinstance(result.facts[0], TrendFact)

    def test_strength_bounded_0_to_1(self) -> None:
        closes = [100.0 + i * 100.0 for i in range(60)]
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)
        result = TrendAnalyzer().analyze(view, facts)
        assert 0.0 <= _trend(result).strength <= 1.0

    def test_evidence_matches_fact_evidence(self) -> None:
        closes = _rising_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)
        result = TrendAnalyzer().analyze(view, facts)
        assert result.evidence == result.facts[0].evidence

    def test_custom_periods(self) -> None:
        closes = _rising_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 10, 30)
        result = TrendAnalyzer(
            fast_key="ema_10", slow_key="ema_30"
        ).analyze(view, facts)
        assert isinstance(result.facts[0], TrendFact)
