from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from marketatlas.data.types import Candle
from marketatlas.facts.structural import TrendDirection
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.trade import TradeCandidate
from marketatlas.strategy.tradebook import TradeBook

pytestmark = pytest.mark.tier1
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
            slippage_pct=0.0,
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

        tb.fill_order(_candle(ts + timedelta(days=1), h=110.0, lo=90.0))
        assert tb.has_pending_order is False
        assert tb.has_no_open_trade is False

    def test_fill_without_pending_noop(self) -> None:
        tb = TradeBook()
        ts = datetime(2024, 1, 1)
        tb.fill_order(_candle(ts, h=110.0, lo=90.0))
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
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

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
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

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
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

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
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

        hit_stop = _candle(t0 + timedelta(days=2), h=106.0, lo=98.0, c=99.0)
        tb.resolve_at_cursor(hit_stop)

        assert tb.has_no_open_trade is True
        assert tb.loss_count == 1
        expected_pnl = (100.0 - 105.0) * 0.2
        assert tb.total_pnl == pytest.approx(expected_pnl)

    def test_max_hold_days_cancels_open_trade(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(entry=100.0, stop=95.0, target=200.0, size=0.2)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

        # Candle at day 11 (10 days after entry), neither stop nor target hit
        still_open = _candle(t0 + timedelta(days=11), h=110.0, lo=99.0, c=108.0)
        tb.resolve_at_cursor(still_open, max_hold_days=10)

        assert tb.has_no_open_trade is True
        assert tb.trades[-1].result == "cancelled"
        assert tb.trades[-1].pnl == 0.0
        assert tb.total_pnl == 0.0

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
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

        # Candle closes exactly at entry → still open (neither stop nor target)
        be_candle = _candle(t0 + timedelta(days=2), o=100.0, h=104.0, lo=96.0, c=100.0)
        tb.resolve_at_cursor(be_candle)
        assert tb.has_no_open_trade is False

        # Close at entry → pnl = 0 → breakeven
        tb.close_trade(100.0, t0 + timedelta(days=2))

        assert tb.breakeven_count == 1
        assert tb.total_pnl == pytest.approx(0.0)

    def test_max_hold_cancels_not_breakeven(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(entry=100.0, stop=95.0, target=105.0, size=0.2)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

        still_open = _candle(t0 + timedelta(days=11), c=100.0)
        tb.resolve_at_cursor(still_open, max_hold_days=10)

        assert tb.trades[-1].result == "cancelled"
        assert tb.breakeven_count == 0


class TestFillCandleResolution:
    """The fill candle may resolve the trade the same day it is placed.

    Entry is re-priced at the fill candle's open (the planned entry came from
    the signal candle), and a gap through stop/target at that open exits at
    the open. Later candles on the same calendar day are not treated as the
    fill candle for gap handling.
    """

    def _fill(
        self,
        tb: TradeBook,
        fill_ts: datetime,
        fill_price: float = 100.0,
        cand: TradeCandidate | None = None,
    ) -> None:
        c = cand or _candidate()
        tb.submit_order(c, _signal(c.direction), "s", datetime(2024, 1, 1))
        tb.fill_order(_candle(fill_ts, h=110.0, lo=90.0))

    def test_fill_uses_submitted_candidate_as_is(self) -> None:
        """Broker fills with the submitted order values; no re-pricing at fill."""
        tb = TradeBook()
        t0 = datetime(2024, 1, 1)
        cand = TradeCandidate(
            direction=TrendDirection.BULLISH,
            entry=100.0,
            stop=95.0,
            target=115.0,
            size=0.2,
            risk_amount=1.0,
            reward_amount=3.0,
            rr_ratio=3.0,
            slippage_pct=0.1,
            source="test",
            evidence=(),
        )
        self._fill(tb, t0 + timedelta(days=1), cand=cand)
        open_trade = tb._open_trade
        assert open_trade is not None
        assert open_trade.candidate is cand
        assert open_trade.candidate.entry == 100.0
        assert open_trade.candidate.size == 0.2
        assert open_trade.candidate.rr_ratio == 3.0

    def test_no_fill_until_entry_crossed(self) -> None:
        """Order stays pending until a bullish candle rises through the entry."""
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = _candidate(entry=100.0, stop=95.0, target=115.0)
        tb.submit_order(cand, _signal(), "s", t0)
        # Bullish: price never rises to entry (high 98 < entry 100) -> no fill
        tb.fill_order(_candle(t0 + timedelta(days=1), h=98.0, lo=90.0))
        assert tb.has_pending_order is True
        assert tb.has_no_open_trade is True
        # Later candle rises through entry (high 102 >= 100) -> fills
        tb.fill_order(_candle(t0 + timedelta(days=2), h=102.0, lo=99.0))
        assert tb.has_pending_order is False
        assert tb.has_no_open_trade is False

    def test_gap_away_from_entry_never_fills(self) -> None:
        """A gap that leaves price below a bullish entry never fills."""
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = _candidate(entry=100.0, stop=95.0, target=115.0)
        tb.submit_order(cand, _signal(), "s", t0)
        for i in range(1, 6):
            tb.fill_order(_candle(t0 + timedelta(days=i), h=99.0, lo=90.0))
        assert tb.has_pending_order is True
        assert tb.has_no_open_trade is True

    def test_bearish_no_fill_until_entry_crossed(self) -> None:
        """Bearish order fills only when price falls to the entry."""
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = _candidate(direction=TrendDirection.BEARISH, entry=100.0, stop=105.0, target=85.0)
        tb.submit_order(cand, _signal(cand.direction), "s", t0)
        # Bearish: price never falls to entry (low 102 > entry 100) -> no fill
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=102.0))
        assert tb.has_pending_order is True
        # Later falls through entry (low 99 <= 100) -> fills
        tb.fill_order(_candle(t0 + timedelta(days=2), h=103.0, lo=99.0))
        assert tb.has_pending_order is False
        assert tb.has_no_open_trade is False

    def test_fill_candle_same_day_target_cross_is_a_win(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        fill_ts = t0 + timedelta(days=1)
        self._fill(tb, fill_ts, cand=_candidate(target=115.0))
        tb.resolve_at_cursor(_candle(fill_ts, o=100.0, h=116.0, lo=99.0, c=114.0))
        assert tb.has_no_open_trade is True
        assert tb.trades[0].result == "win"
        assert tb.trades[0].exit_timestamp == fill_ts
        assert tb.total_pnl == pytest.approx((115.0 - 100.0) * 0.2)

    def test_fill_candle_same_day_stop_cross_is_a_loss(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        fill_ts = t0 + timedelta(days=1)
        self._fill(tb, fill_ts, cand=_candidate(stop=95.0))
        tb.resolve_at_cursor(_candle(fill_ts, o=100.0, h=101.0, lo=94.0, c=96.0))
        assert tb.has_no_open_trade is True
        assert tb.trades[0].result == "loss"
        assert tb.trades[0].exit_timestamp == fill_ts
        assert tb.total_pnl == pytest.approx((95.0 - 100.0) * 0.2)

    def test_later_same_day_candle_does_not_trigger_fill_gap(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        fill_ts = datetime(2024, 1, 11, 10, 0)
        self._fill(tb, fill_ts, cand=_candidate(stop=80.0, target=120.0))
        tb.resolve_at_cursor(_candle(fill_ts, o=100.0, h=101.0, lo=99.0, c=100.0))
        assert tb.has_no_open_trade is False
        later = _candle(datetime(2024, 1, 11, 12, 0), o=130.0, h=131.0, lo=129.0, c=130.0)
        tb.resolve_at_cursor(later)
        assert tb.has_no_open_trade is True
        assert tb.trades[0].result == "win"
        assert tb.total_pnl == pytest.approx((120.0 - 100.0) * 0.2)

    def test_fill_uses_submitted_min_rr_not_refiltered_at_fill(self) -> None:
        """RR is validated at order placement; the broker fills as submitted."""
        tb = TradeBook()
        t0 = datetime(2024, 1, 1)
        cand = replace(_candidate(stop=95.0, target=115.0), min_rr=1.0)
        self._fill(tb, t0 + timedelta(days=1), fill_price=106.0, cand=cand)
        assert tb.has_pending_order is False
        assert tb.has_no_open_trade is False
        assert tb._open_trade is not None
        assert tb._open_trade.candidate is cand


class TestSummary:
    def test_summary_includes_breakevens(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        # Win
        c1 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))

        # Loss
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c2, _signal(), "s", t1)
        tb.fill_order(_candle(t1, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))

        # Breakeven (exit exactly at entry)
        t2 = t0 + timedelta(days=10)
        c3 = _candidate(entry=100.0, stop=95.0, target=200.0, size=0.2)
        tb.submit_order(c3, _signal(), "s", t2)
        tb.fill_order(_candle(t2, h=110.0, lo=90.0))
        tb.close_trade(100.0, t2 + timedelta(days=1))

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
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))

        # Loss: -2.0
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.4)
        tb.submit_order(c2, _signal(), "s", t1)
        tb.fill_order(_candle(t1, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))

        assert tb.max_drawdown == pytest.approx(2.0 / 1004.0)


class TestStrategyBreakdown:
    def test_breakdown_by_strategy(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        # Strategy A: win
        c1 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c1, _signal(), "strat_a", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))

        # Strategy B: loss
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c2, _signal(), "strat_b", t1)
        tb.fill_order(_candle(t1, h=110.0, lo=90.0))
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
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))

        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c2, _signal(), "strat_a", t1, instrument="BTCUSD")
        tb.fill_order(_candle(t1, h=110.0, lo=90.0))
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
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))
        assert tb.trades[0].instrument == ""


class TestProfitFactor:
    def test_profit_factor(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        # Win: +4.0
        c1 = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.4)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))

        # Loss: -2.0
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.4)
        tb.submit_order(c2, _signal(), "s", t1)
        tb.fill_order(_candle(t1, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))

        assert tb.profit_factor == pytest.approx(4.0 / 2.0)

    def test_profit_factor_no_losses(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        c1 = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.4)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))

        assert tb.profit_factor == float("inf")


class TestPeakBalance:
    def test_peak_balance_tracks_high_watermark(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        # Win: balance goes to 1004
        c1 = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.4)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))
        assert tb.peak_balance == pytest.approx(1004.0)

        # Loss: balance drops to 1002
        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.4)
        tb.submit_order(c2, _signal(), "s", t1)
        tb.fill_order(_candle(t1, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))
        assert tb.peak_balance == pytest.approx(1004.0)

    def test_peak_balance_in_summary(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        c1 = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.4)
        tb.submit_order(c1, _signal(), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=111.0, lo=99.0))
        s = tb.summary
        assert "peak_balance" in s
        assert s["peak_balance"] == pytest.approx(1004.0)


class TestMonthlySummary:
    def _close(self, tb: TradeBook, t0: datetime, win: bool) -> None:
        cand = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.4)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        if win:
            tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=108.0))
        else:
            tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), lo=94.0, h=100.0))

    def test_groups_and_sorts_by_entry_month(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        jan = datetime(2024, 1, 3)
        feb = datetime(2024, 2, 5)
        self._close(tb, jan, win=True)
        self._close(tb, datetime(2024, 1, 20), win=False)
        self._close(tb, feb, win=True)

        monthly = tb.monthly_summary()
        assert list(monthly) == ["2024-01", "2024-02"]
        assert monthly["2024-01"]["trades"] == 2
        assert monthly["2024-01"]["wins"] == 1
        assert monthly["2024-01"]["losses"] == 1
        assert monthly["2024-01"]["total_pnl"] == pytest.approx((115.0 - 100.0) * 0.4 + (95.0 - 100.0) * 0.4)
        assert monthly["2024-02"]["trades"] == 1
        assert monthly["2024-02"]["wins"] == 1
        assert monthly["2024-02"]["losses"] == 0

    def test_monthly_growth_compounds_and_frames_gaps(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        self._close(tb, datetime(2024, 1, 3), win=True)  # +6.0 -> 1006.0
        self._close(tb, datetime(2024, 3, 5), win=True)  # +6.0 -> 1012.0

        monthly = tb.monthly_summary()
        assert list(monthly) == ["2024-01", "2024-02", "2024-03"]
        assert monthly["2024-01"]["growth_pct"] == pytest.approx(6.0 / 1000.0 * 100)
        assert monthly["2024-02"]["trades"] == 0
        assert monthly["2024-02"]["total_pnl"] == 0.0
        assert monthly["2024-02"]["growth_pct"] == 0.0
        assert monthly["2024-03"]["growth_pct"] == pytest.approx(6.0 / 1006.0 * 100)

    def test_empty_when_no_closed_trades(self) -> None:
        assert TradeBook(initial_balance=1000.0).monthly_summary() == {}
