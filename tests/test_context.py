from __future__ import annotations

from datetime import UTC, datetime

import pytest
from marketatlas.facts.primitive import ATRFact
from marketatlas.strategy.context import extract_atr_value, trade_context

pytestmark = pytest.mark.tier1


class _StubCurrent:
    def __init__(self, close: float) -> None:
        self.close = close


class _StubView:
    """Structural stand-in for MarketView: trade_context only reads the head of
    the price/volume/high/low series plus the current close."""

    def __init__(
        self,
        prices: tuple[float, ...],
        volumes: tuple[float, ...],
        highs: tuple[float, ...],
        lows: tuple[float, ...],
        close: float,
    ) -> None:
        self.prices = prices
        self.volumes = volumes
        self.highs = highs
        self.lows = lows
        self.current = _StubCurrent(close)


def _view(close: float = 200.0, prices=None, volumes=None, highs=None, lows=None) -> _StubView:
    seq = tuple(float(i) for i in range(1, 120))
    return _StubView(
        prices=prices if prices is not None else seq,
        volumes=volumes if volumes is not None else (1000.0,) * 120,
        highs=highs if highs is not None else seq,
        lows=lows if lows is not None else seq,
        close=close,
    )


def _atr(value: float) -> ATRFact:
    return ATRFact(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        evidence=(),
        value=value,
        period=14,
    )


class TestTradeContext:
    def test_atr_pct_from_scalar_atr(self) -> None:
        ctx = trade_context(_view(close=200.0), atr_value=4.0)
        assert ctx["atr_pct"] == pytest.approx(2.0)

    def test_vol_ratio_current_over_avg(self) -> None:
        vols = (100.0,) * 20 + (250.0,)
        ctx = trade_context(_view(volumes=vols), atr_value=4.0)
        assert ctx["vol_ratio"] == pytest.approx(2.5)

    def test_rng20_atr_range_in_atr_units(self) -> None:
        seq = tuple(float(i) for i in range(1, 101))
        highs = seq + (130.0,) * 19 + (131.0,)
        lows = seq + (100.0,) * 19 + (99.0,)
        view = _view(highs=highs, lows=lows, close=200.0)
        ctx = trade_context(view, atr_value=2.0)
        assert ctx["rng20_atr"] == pytest.approx(16.0)

    def test_trend_eff_positive_drift(self) -> None:
        closes = tuple(float(i) for i in range(1, 80))
        view = _view(prices=closes, close=closes[-1])
        assert trade_context(view)["trend_eff"] == pytest.approx(1.0)

    def test_trend_eff_negative_drift(self) -> None:
        closes = tuple(80.0 - float(i) for i in range(80))
        view = _view(prices=closes, close=closes[-1])
        assert trade_context(view)["trend_eff"] == pytest.approx(-1.0)

    def test_empty_when_nothing_computable(self) -> None:
        view = _StubView((), (), (), (), 0.0)
        assert trade_context(view) == {}

    def test_atr_zero_omits_atr_keys(self) -> None:
        ctx = trade_context(_view(close=200.0), atr_value=0.0)
        assert "atr_pct" not in ctx
        assert "rng20_atr" not in ctx
        assert "trend_eff" in ctx

    def test_short_history_omits_trend_eff(self) -> None:
        view = _StubView((1.0, 2.0), (1.0,), (2.0,), (1.0,), 2.0)
        assert trade_context(view) == {}


class TestExtractAtrValue:
    def test_finds_scalar_atr_fact_by_type(self) -> None:
        atr = _atr(3.2)
        assert extract_atr_value({"atr_14": atr, "ema_20": object()}.values()) == pytest.approx(3.2)

    def test_none_when_no_scalar_atr(self) -> None:
        assert extract_atr_value({"ema_20": object()}) is None
        assert extract_atr_value({}) is None
