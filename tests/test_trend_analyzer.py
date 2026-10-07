from datetime import UTC, datetime

import pytest
from marketatlas.analysis.analyzers.atr import ATRAnalyzer
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.analyzers.trend import TrendAnalyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import TrendDirection, TrendFact


pytestmark = pytest.mark.tier2
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


def _make_ema_facts(view: MarketView, fast_period: int, slow_period: int) -> dict[FactKey, object]:
    fast = EMAAnalyzer(fast_period)
    slow = EMAAnalyzer(slow_period)
    fast_result = fast.analyze(view, {})
    slow_result = slow.analyze(view, {})
    atr = ATRAnalyzer(14)
    atr_result = atr.analyze(view, {})
    return {
        FactKey(fast.instance_key): fast_result.facts[0],
        FactKey(slow.instance_key): slow_result.facts[0],
        FactKey("atr_14"): atr_result.facts[0],
    }


def _trend(result: AnalysisResult) -> TrendFact:
    fact = result.facts[0]
    assert isinstance(fact, TrendFact)
    return fact


class TestTrendAnalyzer:
    def test_requires_empty(self) -> None:
        assert TrendAnalyzer().requires() == (
            FactKey("ema_20"),
            FactKey("ema_50"),
            FactKey("atr_14"),
        )

    def test_produces_trend_fact(self) -> None:
        assert TrendAnalyzer().produces() == (FactKey("trend"),)

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
        gentle_rise = [100.0 + i * 0.1 for i in range(60)]

        store_steep = _make_store(steep_rise)
        view_steep = MarketView(store_steep, cursor=59, window_size=59)
        facts_steep = _make_ema_facts(view_steep, 20, 50)
        result_steep = TrendAnalyzer().analyze(view_steep, facts_steep)

        store_gentle = _make_store(gentle_rise)
        view_gentle = MarketView(store_gentle, cursor=59, window_size=59)
        facts_gentle = _make_ema_facts(view_gentle, 20, 50)
        result_gentle = TrendAnalyzer().analyze(view_gentle, facts_gentle)

        s_steep = _trend(result_steep).strength
        s_gentle = _trend(result_gentle).strength
        assert s_steep > s_gentle
        assert 0.0 < s_gentle <= s_steep <= 1.0

    def test_strength_uses_atr_for_normalization(self) -> None:
        closes = _rising_closes(60)
        store = _make_store(closes)
        view = MarketView(store, cursor=59, window_size=59)
        facts = _make_ema_facts(view, 20, 50)

        result = TrendAnalyzer().analyze(view, facts)

        spread = abs(
            facts[FactKey("ema_20")].value - facts[FactKey("ema_50")].value
        )
        atr_val = facts[FactKey("atr_14")].value
        expected = min(1.0, spread / atr_val) if atr_val > 0 else 0.0
        assert _trend(result).strength == pytest.approx(expected, abs=1e-4)

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
        result = TrendAnalyzer(fast_key="ema_2", slow_key="ema_3").analyze(view, facts)
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
        result = TrendAnalyzer(fast_key="ema_10", slow_key="ema_30").analyze(view, facts)
        assert isinstance(result.facts[0], TrendFact)


class TestFactNameAlias:
    """``name=`` aliases a produced fact without renaming the consumer input.

    ``trend`` requires fixed input names ``ema_20``/``ema_50``, so a
    timeframe-scaled EMA (e.g. period 480 on 1h bars) could not previously be
    wired into it. ``name=`` publishes the scaled EMA under the contract name,
    making timeframe parity expressible in the DSL instead of by code change.
    """

    def test_alias_replaces_default_fact_name(self) -> None:
        analyzer = EMAAnalyzer(480, name="ema_20")
        assert analyzer.instance_key == "ema_20"
        assert analyzer.produces() == (FactKey("ema_20"),)

    def test_no_alias_keeps_derived_name(self) -> None:
        assert EMAAnalyzer(480).instance_key == "ema_480"
        assert EMAAnalyzer(30).instance_key == "ema_30"

    def test_scaled_ema_satisfies_fixed_trend_inputs(self) -> None:
        # Enough history for a 480/1200 pair to have a measurable slope; with a
        # short series both EMAs sit on price and trend is legitimately neutral.
        closes = _rising_closes(800)
        view = MarketView(_make_store(closes), cursor=len(closes) - 1, window_size=800)
        fast = EMAAnalyzer(480, name="ema_20")
        slow = EMAAnalyzer(1200, name="ema_50")
        atr = ATRAnalyzer(14, name="atr_14")
        facts = {
            FactKey("ema_20"): fast.analyze(view, {}).facts[0],
            FactKey("ema_50"): slow.analyze(view, {}).facts[0],
            FactKey("atr_14"): atr.analyze(view, {}).facts[0],
        }
        assert TrendAnalyzer().requires() == (
            FactKey("ema_20"),
            FactKey("ema_50"),
            FactKey("atr_14"),
        )
        result = TrendAnalyzer().analyze(view, facts)
        assert len(result.facts) == 1
        trend_fact = result.facts[0]
        assert isinstance(trend_fact, TrendFact)
        assert trend_fact.direction == TrendDirection.BULLISH

    def test_alias_distinguishes_two_scaled_windows(self) -> None:
        assert EMAAnalyzer(480, name="ema_20").instance_key != (
            EMAAnalyzer(20, name="ema_20b").instance_key
        )
        assert EMAAnalyzer(20).instance_key == "ema_20"
