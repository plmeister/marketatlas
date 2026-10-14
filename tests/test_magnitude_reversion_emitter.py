from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.signals.magnitude_reversion_signal import (
    MagnitudeReversionSignal,
)
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRPoint, ATRSeriesFact
from marketatlas.facts.structural import (
    RangePositionFact,
    SwingFact,
    SwingPoint,
    SwingType,
    TrendDirection,
)
from marketatlas.strategy.atr_risk import AtrBracketRisk
from marketatlas.strategy.loader import load_strategy, validate_config
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.strategy import Strategy

pytestmark = pytest.mark.tier2

BASE = datetime(2024, 1, 1, tzinfo=UTC)
DSL = Path(__file__).resolve().parents[1] / "strategy" / "magnitude_reversion.dsl"


def _view(n: int = 5, cursor: int | None = None, close: float = 100.0) -> MarketView:
    candles = tuple(
        Candle(
            timestamp=BASE + timedelta(days=i),
            open=close,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1000.0,
        )
        for i in range(n)
    )
    data = MarketData(symbol=Symbol("EURUSD"), timeframe=Timeframe.D1, candles=candles)
    return MarketView(MarketStore(data), cursor=n - 1 if cursor is None else cursor, window_size=n)


def _series(value: float, ts: datetime) -> ATRSeriesFact:
    return ATRSeriesFact(
        timestamp=ts,
        evidence=(),
        points=(ATRPoint(timestamp=ts, value=value),),
        period=14,
    )


def _risk_facts(view: MarketView, atr: float) -> dict[FactKey, Fact]:
    pivot_ts = view.timestamps[view.cursor - 2]
    return {
        FactKey("atr_14_series"): _series(atr, pivot_ts),
        FactKey("magnitude_swings"): _swing(SwingType.LOW, pivot_ts, 90.0),
    }


def _swing(kind: SwingType, timestamp: datetime, price: float) -> SwingFact:
    return SwingFact(
        timestamp=BASE,
        evidence=(),
        swings=(SwingPoint(type=kind, timestamp=timestamp, price=price, index=2),),
    )


def _range(position: float | None) -> RangePositionFact:
    return RangePositionFact(
        timestamp=BASE, evidence=(), high=110.0, low=90.0, position=position
    )


def _facts(
    swing: SwingFact | None = None,
    rng: RangePositionFact | None = None,
) -> dict[FactKey, Fact]:
    f: dict[FactKey, Fact] = {}
    if swing is not None:
        f[FactKey("magnitude_swings")] = swing
    if rng is not None:
        f[FactKey("range_position")] = rng
    return f


def _signal(direction: TrendDirection) -> TradeSignal:
    return TradeSignal(
        direction=direction,
        entry_zone=(100.0, 100.0),
        confidence=1.0,
        source="MagnitudeReversionSignal",
        evidence=(),
    )


class TestMagnitudeReversionSignal:
    def test_low_pivot_fades_to_bullish(self) -> None:
        view = _view()
        pivot_ts = view.timestamps[view.cursor - 2]
        facts = _facts(swing=_swing(SwingType.LOW, pivot_ts, 90.0))
        result = MagnitudeReversionSignal().evaluate_with_rejections(view, facts)
        assert result.signal is not None
        assert result.signal.direction == TrendDirection.BULLISH

    def test_high_pivot_inside_range_fades_to_bearish(self) -> None:
        view = _view()
        pivot_ts = view.timestamps[view.cursor - 2]
        facts = _facts(
            swing=_swing(SwingType.HIGH, pivot_ts, 110.0), rng=_range(0.5)
        )
        result = MagnitudeReversionSignal().evaluate_with_rejections(view, facts)
        assert result.signal is not None
        assert result.signal.direction == TrendDirection.BEARISH

    def test_stale_pivot_produces_no_signal(self) -> None:
        view = _view()
        stale_ts = view.timestamps[view.cursor - 3]
        facts = _facts(swing=_swing(SwingType.LOW, stale_ts, 90.0))
        assert MagnitudeReversionSignal().evaluate(view, facts) is None

    def test_short_above_range_is_rejected(self) -> None:
        view = _view()
        pivot_ts = view.timestamps[view.cursor - 2]
        facts = _facts(
            swing=_swing(SwingType.HIGH, pivot_ts, 90.0),
            rng=_range(0.9),
        )
        result = MagnitudeReversionSignal().evaluate_with_rejections(view, facts)
        assert result.signal is None
        assert result.rejections

    def test_short_missing_range_is_rejected(self) -> None:
        view = _view()
        pivot_ts = view.timestamps[view.cursor - 2]
        facts = _facts(swing=_swing(SwingType.HIGH, pivot_ts, 90.0))
        result = MagnitudeReversionSignal().evaluate_with_rejections(view, facts)
        assert result.signal is None

    def test_long_ignores_range_gate(self) -> None:
        view = _view()
        pivot_ts = view.timestamps[view.cursor - 2]
        facts = _facts(
            swing=_swing(SwingType.LOW, pivot_ts, 90.0),
            rng=_range(0.95),
        )
        result = MagnitudeReversionSignal().evaluate_with_rejections(view, facts)
        assert result.signal is not None
        assert result.signal.direction == TrendDirection.BULLISH

    def test_disable_short_filter_allows_breakout_short(self) -> None:
        view = _view()
        pivot_ts = view.timestamps[view.cursor - 2]
        facts = _facts(
            swing=_swing(SwingType.HIGH, pivot_ts, 90.0),
            rng=_range(0.95),
        )
        signal = MagnitudeReversionSignal(enable_short_filter=False)
        result = signal.evaluate_with_rejections(view, facts)
        assert result.signal is not None
        assert result.signal.direction == TrendDirection.BEARISH

    def test_requires_declares_both_facts(self) -> None:
        reqs = {fk.name for fk in MagnitudeReversionSignal().requires()}
        assert reqs == {"magnitude_swings", "range_position"}


class TestAtrBracketRisk:
    def test_bullish_geometry_and_size(self) -> None:
        view = _view(close=100.0)
        facts = _risk_facts(view, 2.0)
        candidate, evidence = AtrBracketRisk(risk_pct=1.0).evaluate(
            _signal(TrendDirection.BULLISH), facts, view, balance=1000.0
        )
        assert candidate is not None
        assert candidate.entry == pytest.approx(100.0)
        assert candidate.stop == pytest.approx(97.0)
        assert candidate.target == pytest.approx(106.0)
        assert candidate.rr_ratio == pytest.approx(2.0)
        assert candidate.size == pytest.approx(10.0 / 3.0)
        assert evidence

    def test_bearish_is_symmetric(self) -> None:
        view = _view(close=100.0)
        facts = _risk_facts(view, 2.0)
        candidate, _ = AtrBracketRisk().evaluate(
            _signal(TrendDirection.BEARISH), facts, view, balance=1000.0
        )
        assert candidate is not None
        assert candidate.stop == pytest.approx(103.0)
        assert candidate.target == pytest.approx(94.0)

    def test_entry_buffer_and_slippage(self) -> None:
        view = _view(close=100.0)
        facts = _risk_facts(view, 2.0)
        candidate, _ = AtrBracketRisk(entry_buffer_atr=1.0, slippage_pct=1.0).evaluate(
            _signal(TrendDirection.BULLISH), facts, view, balance=1000.0
        )
        assert candidate is not None
        assert candidate.entry == pytest.approx(102.0 * 1.01)

    def test_missing_atr_rejects(self) -> None:
        view = _view()
        candidate, evidence = AtrBracketRisk().evaluate(
            _signal(TrendDirection.BULLISH), {}, view
        )
        assert candidate is None
        assert evidence and evidence[0].level == EvidenceLevel.WARNING

    def test_binding_overrides_atr_key(self) -> None:
        view = _view(close=100.0)
        pivot_ts = view.timestamps[view.cursor - 2]
        facts: dict[FactKey, Fact] = {
            FactKey("atr_weekly"): _series(4.0, pivot_ts),
            FactKey("magnitude_swings"): _swing(SwingType.LOW, pivot_ts, 90.0),
        }
        candidate, _ = AtrBracketRisk(
            bindings={"atr_14_series": "atr_weekly"}
        ).evaluate(
            _signal(TrendDirection.BULLISH), facts, view, balance=1000.0
        )
        assert candidate is not None
        assert candidate.stop == pytest.approx(94.0)

    def test_atr_read_at_pivot_bar_not_signal_bar(self) -> None:
        view = _view(close=100.0)
        pivot_ts = view.timestamps[view.cursor - 2]
        signal_ts = view.timestamps[view.cursor]
        series = ATRSeriesFact(
            timestamp=signal_ts,
            evidence=(),
            points=(
                ATRPoint(timestamp=pivot_ts, value=2.0),
                ATRPoint(timestamp=signal_ts, value=99.0),
            ),
            period=14,
        )
        facts: dict[FactKey, Fact] = {
            FactKey("atr_14_series"): series,
            FactKey("magnitude_swings"): _swing(SwingType.LOW, pivot_ts, 90.0),
        }
        candidate, _ = AtrBracketRisk().evaluate(
            _signal(TrendDirection.BULLISH), facts, view, balance=1000.0
        )
        assert candidate is not None
        assert candidate.stop == pytest.approx(97.0)

    def test_missing_swing_rejects(self) -> None:
        view = _view(close=100.0)
        facts: dict[FactKey, Fact] = {
            FactKey("atr_14_series"): _series(2.0, view.timestamps[view.cursor - 2])
        }
        candidate, evidence = AtrBracketRisk().evaluate(
            _signal(TrendDirection.BULLISH), facts, view
        )
        assert candidate is None
        assert evidence and evidence[0].level == EvidenceLevel.WARNING

    @pytest.mark.parametrize("bad", [{"stop_atr": 0.0}, {"target_atr": -1.0}])
    def test_rejects_bad_geometry(self, bad: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            AtrBracketRisk(**bad)


class TestDslWiring:
    def test_loads_and_validates(self) -> None:
        config = load_strategy(DSL)
        assert validate_config(config) == []
        assert config.risk.algorithm == "AtrBracketRisk"
        assert [s.type for s in config.signals] == ["MagnitudeReversionSignal"]

    def test_strategy_builds_with_new_nodes(self) -> None:
        config = load_strategy(DSL)
        strategy = Strategy("magnitude_reversion", config)
        assert isinstance(strategy.risk_engine, AtrBracketRisk)
        assert config.risk.params["stop_atr"] == 1.5
        assert config.risk.params["target_atr"] == 3.0
        assert [s.type for s in config.signals] == ["MagnitudeReversionSignal"]
