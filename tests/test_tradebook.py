from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from marketatlas.data.types import Candle
from marketatlas.facts.structural import TrendDirection
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.trade import TradeCandidate
from marketatlas.strategy.tradebook import TradeBook


def _candle(
    ts: datetime,
    o: float = 100.0,
    h: float = 105.0,
    lo: float = 95.0,
    c: float = 102.0,
) -> Candle:
    return Candle(timestamp=ts, open=o, high=h, low=lo, close=c, volume=1000.0)


def _signal(direction: TrendDirection = TrendDirection.BULLISH) -> TradeSignal:
    return TradeSignal(
        direction=direction,
        entry_zone=(99.0, 101.0),
        confidence=0.8,
        source="test",
        evidence=(),
    )


def _candidate(
    direction: TrendDirection = TrendDirection.BULLISH,
    entry: float = 100.0,
    stop: float = 95.0,
    target: float = 115.0,
    size: float = 0.2,
) -> TradeCandidate:
    risk_amount = abs(entry - stop) * size
    reward_amount = abs(target - entry) * size
    rr = abs(target - entry) / abs(entry - stop) if entry != stop else 0.0
    return TradeCandidate(
        direction=direction,
        entry=entry,
        stop=stop,
        target=target,
        size=size,
        risk_amount=risk_amount,
        reward_amount=reward_amount,
        rr_ratio=rr,
        slippage_pct=0.1,
        source="test",
        evidence=(),
    )


class TestTradeBookBasics:
    def test_initial_state(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        assert tb.balance == 1000.0
        assert tb.initial_balance == 1000.0
        assert tb.peak_balance == 1000.0
        assert tb.trades == ()
        assert tb.has_no_open_trade is True
        assert tb.has_pending_order is False
        assert tb.win_count == 0
        assert tb.loss_count == 0
        assert tb.breakeven_count == 0
        assert tb.closed_count == 0
        assert tb.total_pnl == 0.0

    def test_submit_and_fill_order(self) -> None:
        tb = TradeBook()
        ts = datetime(2024, 1, 1)
        cand = _candidate()
        sig = _signal()

        tb.submit_order(cand, sig, "strat1", ts)
        assert tb.has_pending_order is True
        assert tb.has_no_open_trade is True

        tb.fill_order(100.0, ts + timedelta(days=1))
        assert tb.has_pending_order is False
        assert tb.has_no_open_trade is False

    def test_fill_without_pending_noop(self) -> None:
        tb = TradeBook()
        ts = datetime(2024, 1, 1)
        tb.fill_order(100.0, ts)
        assert tb.has_no_open_trade is True


class TestCloseTradeNoop:
    def test_close_trade_no_open_trade(self) -> None:
        tb = TradeBook()
        ts = datetime(2024, 1, 1)
        tb.close_trade(100.0, ts)
        assert tb.has_no_open_trade is True
        assert tb.balance == tb.initial_balance


class TestTradeResolution:
    def test_bullish_win(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(100.0, t0 + timedelta(days=1))

        hit_target = _candle(t0 + timedelta(days=2), h=116.0, lo=99.0, c=114.0)
        tb.resolve_at_cursor(hit_target)

        assert tb.has_no_open_trade is True
        assert tb.win_count == 1
        assert tb.closed_count == 1
        expected_pnl = (115.0 - 100.0) * 0.2
        assert tb.total_pnl == pytest.approx(expected_pnl)

    def test_bullish_loss(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(100.0, t0 + timedelta(days=1))

        hit_stop = _candle(t0 + timedelta(days=2), h=101.0, lo=94.0, c=96.0)
        tb.resolve_at_cursor(hit_stop)

        assert tb.has_no_open_trade is True
        assert tb.loss_count == 1
        expected_pnl = (95.0 - 100.0) * 0.2
        assert tb.total_pnl == pytest.approx(expected_pnl)

    def test_bearish_win(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(
            direction=TrendDirection.BEARISH,
            entry=100.0,
            stop=105.0,
            target=85.0,
            size=0.2,
        )
        tb.submit_order(cand, _signal(TrendDirection.BEARISH), "s", t0)
        tb.fill_order(100.0, t0 + timedelta(days=1))

        hit_target = _candle(t0 + timedelta(days=2), h=101.0, lo=84.0, c=86.0)
        tb.resolve_at_cursor(hit_target)

        assert tb.win_count == 1
        expected_pnl = (100.0 - 85.0) * 0.2
        assert tb.total_pnl == pytest.approx(expected_pnl)

    def test_bearish_stop_hit(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(
            direction=TrendDirection.BEARISH,
            entry=100.0,
            stop=105.0,
            target=85.0,
            size=0.2,
        )
        tb.submit_order(cand, _signal(TrendDirection.BEARISH), "s", t0)
        tb.fill_order(100.0, t0 + timedelta(days=1))

        hit_stop = _candle(t0 + timedelta(days=2), h=106.0, lo=98.0, c=99.0)
        tb.resolve_at_cursor(hit_stop)

        assert tb.has_no_open_trade is True
        assert tb.loss_count == 1
        expected_pnl = (100.0 - 105.0) * 0.2
        assert tb.total_pnl == pytest.approx(expected_pnl)

    def test_max_hold_days_force_close(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(entry=100.0, stop=95.0, target=200.0, size=0.2)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(100.0, t0 + timedelta(days=1))

        # Candle at day 11 (10 days after entry)
        still_open = _candle(t0 + timedelta(days=11), h=110.0, lo=99.0, c=108.0)
        tb.resolve_at_cursor(still_open, max_hold_days=10)

        assert tb.has_no_open_trade is True
        assert tb.win_count == 1

    def test_no_resolution_without_trade(self) -> None:
        tb = TradeBook()
        candle = _candle(datetime(2024, 1, 1))
        tb.resolve_at_cursor(candle)
        assert tb.has_no_open_trade is True


class TestBreakevenCount:
    def test_breakeven_trade(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(entry=100.0, stop=95.0, target=105.0, size=0.2)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(100.0, t0 + timedelta(days=1))

        # Candle closes exactly at entry → pnl = 0
        be_candle = _candle(t0 + timedelta(days=2), o=100.0, h=104.0, lo=96.0, c=100.0)
        tb.resolve_at_cursor(be_candle)

        # Neither hit stop (95) nor target (105) → still open
        assert tb.has_no_open_trade is False

        # Force close via max hold
        close_candle = _candle(t0 + timedelta(days=11), c=100.0)
        tb.resolve_at_cursor(close_candle, max_hold_days=10)

        assert tb.breakeven_count == 1
        assert tb.total_pnl == pytest.approx(0.0)


class TestSummary:
    def test_summary_includes_breakevens(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        # Win
        c1 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(100.0, t0)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))

        # Loss
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c2, _signal(), "s", t1)
        tb.fill_order(100.0, t1)
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))

        # Breakeven
        t2 = t0 + timedelta(days=10)
        c3 = _candidate(entry=100.0, stop=95.0, target=200.0, size=0.2)
        tb.submit_order(c3, _signal(), "s", t2)
        tb.fill_order(100.0, t2)
        tb.resolve_at_cursor(
            _candle(t2 + timedelta(days=11), h=110.0, lo=99.0, c=100.0),
            max_hold_days=10,
        )

        s = tb.summary
        assert s["total_trades"] == 3
        assert s["wins"] == 1
        assert s["losses"] == 1
        assert s["breakevens"] == 1
        total = int(s["total_trades"])  # type: ignore[arg-type]
        wins = int(s["wins"])  # type: ignore[arg-type]
        losses = int(s["losses"])  # type: ignore[arg-type]
        be = int(s["breakevens"])  # type: ignore[arg-type]
        assert total == wins + losses + be


class TestMaxDrawdown:
    def test_drawdown_after_loss(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        # Win: +4.0
        c1 = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.4)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(100.0, t0)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))

        # Loss: -2.0
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.4)
        tb.submit_order(c2, _signal(), "s", t1)
        tb.fill_order(100.0, t1)
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))

        assert tb.max_drawdown == pytest.approx(2.0 / 1004.0)


class TestStrategyBreakdown:
    def test_breakdown_by_strategy(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        # Strategy A: win
        c1 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c1, _signal(), "strat_a", t0)
        tb.fill_order(100.0, t0)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))

        # Strategy B: loss
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c2, _signal(), "strat_b", t1)
        tb.fill_order(100.0, t1)
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))

        bd = tb.summary["by_strategy"]
        assert isinstance(bd, dict)
        assert bd["strat_a"]["wins"] == 1  # type: ignore[index]
        assert bd["strat_a"]["losses"] == 0  # type: ignore[index]
        assert bd["strat_b"]["wins"] == 0  # type: ignore[index]
        assert bd["strat_b"]["losses"] == 1  # type: ignore[index]

    def test_breakdown_by_instrument(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        c1 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c1, _signal(), "strat_a", t0, instrument="GBPUSD")
        tb.fill_order(100.0, t0)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))

        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c2, _signal(), "strat_a", t1, instrument="BTCUSD")
        tb.fill_order(100.0, t1)
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))

        trades = tb.trades
        assert trades[0].instrument == "GBPUSD"
        assert trades[1].instrument == "BTCUSD"

        bd = tb.summary["by_instrument"]
        assert isinstance(bd, dict)
        assert bd["GBPUSD"]["wins"] == 1  # type: ignore[index]
        assert bd["GBPUSD"]["losses"] == 0  # type: ignore[index]
        assert bd["BTCUSD"]["wins"] == 0  # type: ignore[index]
        assert bd["BTCUSD"]["losses"] == 1  # type: ignore[index]
        assert bd["BTCUSD"]["total_pnl"] < 0  # type: ignore[index]

    def test_instrument_defaults_empty(self) -> None:
        tb = TradeBook()
        t0 = datetime(2024, 1, 1)
        c1 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(100.0, t0)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))
        assert tb.trades[0].instrument == ""


class TestProfitFactor:
    def test_profit_factor(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        # Win: +4.0
        c1 = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.4)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(100.0, t0)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))

        # Loss: -2.0
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.4)
        tb.submit_order(c2, _signal(), "s", t1)
        tb.fill_order(100.0, t1)
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))

        assert tb.profit_factor == pytest.approx(4.0 / 2.0)

    def test_profit_factor_no_losses(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        c1 = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.4)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(100.0, t0)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))

        assert tb.profit_factor == float("inf")


class TestPeakBalance:
    def test_peak_balance_tracks_high_watermark(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        # Win: balance goes to 1004
        c1 = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.4)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(100.0, t0)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))
        assert tb.peak_balance == pytest.approx(1004.0)

        # Loss: balance drops to 1002
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.4)
        tb.submit_order(c2, _signal(), "s", t1)
        tb.fill_order(100.0, t1)
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))
        assert tb.peak_balance == pytest.approx(1004.0)

    def test_peak_balance_in_summary(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        c1 = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.4)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(100.0, t0)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))
        s = tb.summary
        assert "peak_balance" in s
        assert s["peak_balance"] == pytest.approx(1004.0)
