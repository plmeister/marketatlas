from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from marketatlas.data.types import Candle
from marketatlas.facts.structural import TrendDirection
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.trade import ExitPlan, ExitReason, TradeCandidate
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
    exit_plan: ExitPlan | None = None,
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
            exit_plan=exit_plan,
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


def _at_open_candidate(
    direction: TrendDirection = TrendDirection.BULLISH,
    entry: float = 100.0,
    stop: float = 95.0,
    target: float = 115.0,
    size: float = 0.2,
) -> TradeCandidate:
    return _candidate(direction=direction, entry=entry, stop=stop, target=target, size=size)
class TestAtOpenFill:
    """EOD → next-open execution (entry_at_open)."""

    def test_fills_at_next_candle_open(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = _at_open_candidate()
        cand = replace(cand, entry_at_open=True, reference_price=100.0)

        tb.submit_order(cand, _signal(), "s", t0)
        # Next day opens at 102 -> fill 102, not the planned 100.
        tb.fill_order(_candle(t0 + timedelta(days=1), o=102.0, h=110.0, lo=95.0))
        assert tb.has_no_open_trade is False
        open_trade = tb._open_trades[""]
        assert open_trade.entry_timestamp == t0 + timedelta(days=1)
        assert open_trade.candidate.entry == pytest.approx(102.0)

    def test_gap_guard_skips_big_gap(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = replace(
            _at_open_candidate(),
            entry_at_open=True,
            reference_price=100.0,
            max_open_gap=5.0,
        )
        tb.submit_order(cand, _signal(), "s", t0)
        # Open gapped +8 from the reference close -> beyond the 5.0 band.
        tb.fill_order(_candle(t0 + timedelta(days=1), o=108.0, h=112.0, lo=100.0))
        assert tb.has_pending_order is False
        assert tb.has_no_open_trade is True
        assert any(t.result == "cancelled" for t in tb.trades)

    def test_gap_within_band_fills(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = replace(
            _at_open_candidate(),
            entry_at_open=True,
            reference_price=100.0,
            max_open_gap=5.0,
        )
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), o=102.0, h=110.0, lo=95.0))
        assert tb.has_no_open_trade is False

    def test_open_beyond_stop_declined(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = replace(_at_open_candidate(), entry_at_open=True)
        tb.submit_order(cand, _signal(), "s", t0)
        # Open below the 95 stop -> entry never existed.
        tb.fill_order(_candle(t0 + timedelta(days=1), o=93.0, h=98.0, lo=92.0))
        assert tb.has_no_open_trade is True
        assert any(t.result == "cancelled" for t in tb.trades)

    def test_open_beyond_target_declined(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = replace(_at_open_candidate(), entry_at_open=True)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), o=118.0, h=120.0, lo=100.0))
        assert tb.has_no_open_trade is True
        assert any(t.result == "cancelled" for t in tb.trades)

    def test_reanchor_preserves_risk_and_rr(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = replace(_at_open_candidate(), entry_at_open=True)
        # Planned stop 95 -> stop distance 5; risk_amount = 5 * 0.2 = 1.0.
        assert cand.risk_amount == pytest.approx(1.0)
        tb.submit_order(cand, _signal(), "s", t0)
        # Open at 102 -> stop distance 7; size shrinks to keep risk = 1.0.
        tb.fill_order(_candle(t0 + timedelta(days=1), o=102.0, h=110.0, lo=95.0))
        open_c = tb._open_trades[""].candidate
        assert open_c.entry == pytest.approx(102.0)
        assert open_c.stop == pytest.approx(95.0)
        assert open_c.risk_amount == pytest.approx(1.0)
        assert open_c.size == pytest.approx(1.0 / 7.0)
        assert open_c.rr_ratio == pytest.approx(cand.rr_ratio)
        assert open_c.target == pytest.approx(102.0 + cand.rr_ratio * 7.0)

    def test_touch_model_untouched_by_new_fields(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        cand = _candidate()
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))
        assert tb._open_trades[""].candidate.entry == pytest.approx(100.0)


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
        assert tb.trades[-1].exit_reason is ExitReason.TARGET
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
        assert tb.trades[-1].exit_reason is ExitReason.STOP
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
        assert tb.trades[-1].exit_reason is ExitReason.TARGET
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
        assert tb.trades[-1].exit_reason is ExitReason.STOP
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
        assert tb.trades[-1].exit_reason is ExitReason.TIMEOUT
        assert tb.total_pnl == 0.0

    def test_boundary_candle_target_hit_closes_win_not_cancel(self) -> None:
        """Target touched on the max-hold boundary candle must close as a win
        (backlog 104 — AUDJPY 2026-01-29 hit target on day 10 but was recorded
        cancelled)."""
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

        boundary = _candle(t0 + timedelta(days=11), h=116.0, lo=99.0, c=114.0)
        tb.resolve_at_cursor(boundary, max_hold_days=10)

        assert tb.has_no_open_trade is True
        assert tb.trades[-1].result == "win"
        assert tb.trades[-1].exit_reason is ExitReason.TARGET
        expected_pnl = (115.0 - 100.0) * 0.2
        assert tb.total_pnl == pytest.approx(expected_pnl)

    def test_boundary_candle_stop_hit_closes_loss_not_cancel(self) -> None:
        """Stop touched on the max-hold boundary candle must close as a loss
        instead of being cancelled at pnl 0."""
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(entry=100.0, stop=95.0, target=200.0, size=0.2)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

        boundary = _candle(t0 + timedelta(days=11), h=110.0, lo=94.0, c=96.0)
        tb.resolve_at_cursor(boundary, max_hold_days=10)

        assert tb.has_no_open_trade is True
        assert tb.trades[-1].result == "loss"
        assert tb.trades[-1].exit_reason is ExitReason.STOP
        expected_pnl = (95.0 - 100.0) * 0.2
        assert tb.total_pnl == pytest.approx(expected_pnl)

    def test_bearish_boundary_candle_target_hit_closes_win(self) -> None:
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

        boundary = _candle(t0 + timedelta(days=11), h=101.0, lo=84.0, c=86.0)
        tb.resolve_at_cursor(boundary, max_hold_days=10)

        assert tb.has_no_open_trade is True
        assert tb.trades[-1].result == "win"
        assert tb.trades[-1].exit_reason is ExitReason.TARGET
        expected_pnl = (100.0 - 85.0) * 0.2
        assert tb.total_pnl == pytest.approx(expected_pnl)

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
        assert tb.trades[-1].exit_reason is None

    def test_max_hold_cancels_not_breakeven(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        cand = _candidate(entry=100.0, stop=95.0, target=105.0, size=0.2)
        tb.submit_order(cand, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))

        still_open = _candle(t0 + timedelta(days=11), h=104.0, lo=96.0, c=100.0)
        tb.resolve_at_cursor(still_open, max_hold_days=10)

        assert tb.trades[-1].result == "cancelled"
        assert tb.trades[-1].exit_reason is ExitReason.TIMEOUT
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
        open_trade = tb._open_trades[""]
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
        assert tb._open_trades[""] is not None
        assert tb._open_trades[""].candidate is cand


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
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0), "GBPUSD")
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=116.0, lo=99.0), instrument="GBPUSD")

        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c2, _signal(), "strat_a", t1, instrument="BTCUSD")
        tb.fill_order(_candle(t1 + timedelta(days=1), h=110.0, lo=90.0), "BTCUSD")
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=2), lo=94.0, h=101.0), instrument="BTCUSD")

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
        assert monthly["2024-01"]["total_pnl"] == pytest.approx(
            (115.0 - 100.0) * 0.4 + (95.0 - 100.0) * 0.4
        )
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


class TestRBasedMetrics:
    """R-multiple edge metrics (backlog: growth measurement).

    Each trade's outcome in R units: pnl / risk_amount. `_candidate` with
    entry=100/stop=95/target=115/size=0.2 has risk_amount=1.0, so target hit
    -> +3.0 P&L = +3R, stop hit -> -1.0 P&L = -1R.
    """

    def test_empty_book(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        assert tb.avg_win_r == 0.0
        assert tb.avg_loss_r == 0.0
        assert tb.expectancy_in_r == 0.0
        assert tb.kelly_fraction == 0.0
        assert tb.payoff_ratio == 0.0
        assert tb.trades_per_year == 0.0
        assert tb.by_direction == {}

    def test_win_and_loss_r(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)

        c1 = _candidate(entry=100.0, stop=95.0, target=115.0)  # risk 1.0
        sig = _signal()
        tb.submit_order(c1, sig, "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))  # target -> +3R

        t1 = t0 + timedelta(days=5)
        c2 = _candidate(entry=100.0, stop=95.0, target=115.0)
        tb.submit_order(c2, _signal(), "s", t1)
        tb.fill_order(_candle(t1, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), lo=94.0, h=101.0))  # stop -> -1R

        assert tb.win_rate == 0.5
        assert tb.avg_win_r == pytest.approx(3.0)
        assert tb.avg_loss_r == pytest.approx(1.0)
        assert tb.payoff_ratio == pytest.approx(3.0)
        assert tb.expectancy_in_r == pytest.approx(0.5 * 3.0 - 0.5 * 1.0)  # 1.0
        assert tb.kelly_fraction == pytest.approx(0.5 - 0.5 * 1.0 / 3.0)

    def test_kelly_zero_without_edge(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        # Same-R win then loss: E = 0 -> Kelly 0.
        for i in range(2):
            c = _candidate(entry=100.0, stop=95.0, target=110.0, size=0.2)  # +2R target
            tb.submit_order(c, _signal(), "s", t0 + timedelta(days=i))
            tb.fill_order(_candle(t0 + timedelta(days=i), h=110.0, lo=90.0))
            win = bool(i % 2 == 0)
            tb.resolve_at_cursor(
                _candle(t0 + timedelta(days=i, hours=12), h=111.0, lo=89.0)
                if win
                else _candle(t0 + timedelta(days=i, hours=12), h=111.0, lo=94.0)
            )
        assert tb.by_direction["bullish"]["trades"] == 2
        assert tb.kelly_fraction == 0.0

    def test_by_direction(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        bull = _candidate(entry=100.0, stop=95.0, target=115.0)
        tb.submit_order(bull, _signal(), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))

        t1 = t0 + timedelta(days=5)
        bear = _candidate(direction=TrendDirection.BEARISH, entry=100.0, stop=105.0, target=85.0)
        tb.submit_order(bear, _signal(), "s", t1)
        tb.fill_order(_candle(t1, h=110.0, lo=90.0))  # low 90 <= 100 -> fill
        tb.resolve_at_cursor(_candle(t1 + timedelta(days=1), h=90.0, lo=80.0))  # low 80 -> target

        by_dir = tb.by_direction
        assert by_dir["bullish"]["trades"] == 1
        assert by_dir["bullish"]["wins"] == 1
        assert by_dir["bullish"]["win_rate"] == 1.0
        assert by_dir["bearish"]["trades"] == 1
        assert by_dir["bearish"]["wins"] == 1
        assert by_dir["bearish"]["win_rate"] == 1.0

    def test_trades_per_year_spans_first_to_last_exit(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        jan = datetime(2024, 1, 1)
        c = _candidate(entry=100.0, stop=95.0, target=115.0)
        tb.submit_order(c, _signal(), "s", jan)
        tb.fill_order(_candle(jan, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(jan + timedelta(days=1), h=116.0, lo=99.0))  # exit day 1
        # Second trade ~365 days later: span ~365 days, 2 trades -> ~2/yr.
        second = jan.replace(year=2025)
        tb.submit_order(_candidate(), _signal(), "s", second)
        tb.fill_order(_candle(second, h=110.0, lo=90.0))
        tb.close_trade(116.0, second + timedelta(days=1))
        assert tb.trades_per_year == pytest.approx(2.0, rel=0.02)

    def test_summary_carries_r_metrics(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        c = _candidate(entry=100.0, stop=95.0, target=115.0)
        tb.submit_order(c, _signal(), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))  # +3R
        s = tb.summary
        assert s["avg_win_r"] == pytest.approx(3.0)
        assert s["expectancy_in_r"] == pytest.approx(3.0)
        assert s["payoff_ratio"] == float("inf")
        assert s["by_direction"]["bullish"]["wins"] == 1  # type: ignore[index]


def _plan(
    fraction: float = 0.5,
    scale_rr: float = 1.0,
    breakeven: bool = True,
    runner_rr: float = 0.0,
    trail_rr: float = 0.0,
) -> ExitPlan:
    return ExitPlan(
        scale_out_fraction=fraction,
        scale_out_rr=scale_rr,
        breakeven_after_scale=breakeven,
        runner_target_rr=runner_rr,
        trailing_stop_rr=trail_rr,
    )


def _ratchet_plan(breakeven_rr: float = 0.5) -> ExitPlan:
    return ExitPlan(
        scale_out_fraction=0.0,
        scale_out_rr=1.0,
        breakeven_after_scale=True,
        runner_target_rr=0.0,
        trailing_stop_rr=0.0,
        breakeven_at_rr=breakeven_rr,
    )


class TestDeRiskExits:
    """De-risk (scale-out) exits: bank a fraction at scale R, let the runner go.

    Geometry: bull entry=100 stop=95 target=115 (~3R), size=0.2, risk=1.0.
    Scale-out at 1.0R (price 105) banks 0.5 * 1R = +0.5. The remainder (size
    0.1) runs from the breakeven/trail stop toward the runner target.
    Scale candles keep their low above entry (101) so the freshly-armed
    breakeven stop isn't breached on the very candle that triggers scale-out.
    """

    def _open(
        self, plan: ExitPlan, direction: TrendDirection = TrendDirection.BULLISH
    ) -> tuple[TradeBook, datetime, TradeCandidate]:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        if direction == TrendDirection.BULLISH:
            c = _candidate(entry=100.0, stop=95.0, target=115.0, exit_plan=plan)
        else:
            c = _candidate(
                direction=direction, entry=100.0, stop=105.0, target=85.0, exit_plan=plan
            )
        tb.submit_order(c, _signal(direction), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        return tb, t0, c

    def test_scale_out_then_breakeven_banks_partial(self) -> None:
        tb, t0, _ = self._open(_plan(fraction=0.5, scale_rr=1.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=106.0, lo=101.0))
        assert tb.has_no_open_trade is False
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=101.0, lo=99.0, c=100.0))
        assert tb.has_no_open_trade is True
        assert tb.win_count == 1
        assert tb.trades[0].pnl == pytest.approx(0.5)  # banked 0.5R, runner flat
        assert tb.trades[0].result == "win"
        assert tb.trades[0].exit_reason is ExitReason.STOP

    def test_scale_out_then_runner_target_extends_win(self) -> None:
        tb, t0, _ = self._open(_plan(fraction=0.5, scale_rr=1.0, runner_rr=2.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=106.0, lo=101.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=111.0, lo=101.0, c=110.0))
        assert tb.win_count == 1
        # banked 0.5R + runner 0.1 size * 10 pts = 1.0R
        assert tb.trades[0].pnl == pytest.approx(1.5)
        assert tb.trades[0].exit_reason is ExitReason.TARGET

    def test_stop_before_scale_out_is_full_loss(self) -> None:
        tb, t0, _ = self._open(_plan())
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=101.0, lo=94.0))
        assert tb.loss_count == 1
        assert tb.trades[0].pnl == pytest.approx(-1.0)
        assert tb.trades[0].exit_reason is ExitReason.STOP

    def test_unscaled_max_hold_still_cancels_at_zero(self) -> None:
        tb, t0, _ = self._open(_plan(scale_rr=3.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=104.0, lo=97.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=10), h=104.0, lo=97.0), max_hold_days=10)
        closed = tb.trades[0]
        assert closed.result == "cancelled"
        assert closed.pnl == pytest.approx(0.0)
        assert closed.exit_reason is ExitReason.TIMEOUT

    def test_ratchet_arms_then_breakeven_instead_of_loss(self) -> None:
        tb, t0, _ = self._open(_ratchet_plan())
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=103.0, lo=101.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=101.0, lo=99.0, c=100.0))
        closed = tb.trades[0]
        assert tb.loss_count == 0
        assert tb.breakeven_count == 1
        assert closed.pnl == pytest.approx(0.0)
        assert closed.result == "breakeven"
        assert closed.exit_reason is ExitReason.STOP

    def test_ratchet_arms_then_wins_unchanged(self) -> None:
        tb, t0, _ = self._open(_ratchet_plan())
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=103.0, lo=101.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=116.0, lo=110.0, c=115.0))
        closed = tb.trades[0]
        assert tb.win_count == 1
        assert closed.pnl == pytest.approx(3.0)
        assert closed.exit_reason is ExitReason.TARGET

    def test_ratchet_stop_before_arm_is_full_loss(self) -> None:
        tb, t0, _ = self._open(_ratchet_plan())
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=101.0, lo=94.0))
        closed = tb.trades[0]
        assert tb.loss_count == 1
        assert closed.pnl == pytest.approx(-1.0)
        assert closed.exit_reason is ExitReason.STOP

    def test_ratchet_poor_man_stop_after_ratchet_is_zero(self) -> None:
        tb, t0, _ = self._open(_ratchet_plan(breakeven_rr=0.25))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=103.0, lo=101.5))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=101.0, lo=99.0, c=100.0))
        assert tb.loss_count == 0
        assert tb.breakeven_count == 1

    def test_scaled_max_hold_closes_remainder_at_market(self) -> None:
        tb, t0, _ = self._open(_plan(fraction=0.5, scale_rr=1.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=106.0, lo=101.0))
        for d in range(2, 6):
            tb.resolve_at_cursor(
                _candle(t0 + timedelta(days=d), h=108.0, lo=100.5, c=103.0),
                max_hold_days=5,
            )
        assert tb.has_no_open_trade is True
        closed = tb.trades[0]
        assert closed.result == "win"
        # banked 0.5 + runner 0.1 size * (103 - 100) = 0.3 -> 0.8
        assert closed.pnl == pytest.approx(0.8)
        assert closed.exit_reason is ExitReason.TIMEOUT

    def test_bearish_scale_out_banks_partial(self) -> None:
        tb, t0, _ = self._open(_plan(), direction=TrendDirection.BEARISH)
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=99.0, lo=94.0))  # scale at 95
        assert tb.has_no_open_trade is False
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=101.0, lo=99.0))  # breakeven
        assert tb.win_count == 1
        assert tb.trades[0].pnl == pytest.approx(0.5)

    def test_trailing_stop_ratchets_runner_profit(self) -> None:
        tb, t0, _ = self._open(_plan(fraction=0.5, scale_rr=1.0, trail_rr=0.5))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=106.0, lo=104.0))
        assert tb.has_no_open_trade is False  # trail 103.5, low 104 survives
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=108.0, lo=106.0))  # trail 105.5
        assert tb.has_no_open_trade is False  # low 106 > trail 105.5, survives
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=3), h=107.0, lo=103.0))  # breach
        assert tb.has_no_open_trade is True
        # trail = 108 - 0.5*5 = 105.5; runner 0.1 * 5.5 = 0.55; + banked 0.5
        assert tb.trades[0].pnl == pytest.approx(1.05)

    def test_trail_never_loosens_on_pullback(self) -> None:
        tb, t0, _ = self._open(_plan(fraction=0.5, scale_rr=1.0, trail_rr=0.5))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=106.0, lo=104.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=108.0, lo=106.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=3), h=111.0, lo=109.0))  # extreme 111
        assert tb.has_no_open_trade is False  # trail 108.5, low 109 survives
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=4), h=106.0, lo=103.0))  # breach
        # trail stays 108.5 (never loosened to 105.5); runner 0.1 * 8.5 = 0.85; + 0.5
        assert tb.trades[0].pnl == pytest.approx(1.35)

    def test_breakeven_off_lets_remainder_run_to_max_hold(self) -> None:
        tb, t0, _ = self._open(_plan(fraction=0.5, breakeven=False))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=106.0, lo=101.0))
        for d in range(2, 6):
            tb.resolve_at_cursor(
                _candle(t0 + timedelta(days=d), h=108.0, lo=103.0, c=107.0),
                max_hold_days=5,
            )
        assert tb.has_no_open_trade is True
        # banked 0.5 + runner 0.1 * 7 = 0.7 -> 1.2
        assert tb.trades[0].pnl == pytest.approx(1.2)

    def test_r_metrics_spread_with_scale_out(self) -> None:
        tb, t0, _ = self._open(_plan(fraction=0.5, scale_rr=1.0, runner_rr=2.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=106.0, lo=101.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=111.0, lo=101.0, c=110.0))
        assert tb.avg_win_r == pytest.approx(1.5)
        assert tb.expectancy_in_r == pytest.approx(1.5)

    def test_default_exit_stays_byte_identical(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        c = _candidate(entry=100.0, stop=95.0, target=115.0)
        tb.submit_order(c, _signal(), "s", t0)
        tb.fill_order(_candle(t0, h=110.0, lo=90.0))
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=1), h=116.0, lo=99.0))
        assert tb.trades[0].pnl == pytest.approx(3.0)
        assert tb.trades[0].result == "win"
        assert tb.avg_win_r == pytest.approx(3.0)


class TestExitReasons:
    """Exit-reason provenance (backlog 098): every close path records how the
    trade left the book — stop/target/timeout/cancel — without disturbing the
    existing result mapping (win/loss/breakeven/cancelled stay pnl-derived)."""

    def test_pending_order_cancel_reason_cancel(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        c = _candidate(entry=100.0, stop=95.0, target=115.0)
        tb.submit_order(c, _signal(), "s", t0)
        # Entry never reached within max_hold_days -> pending dropped.
        no_touch = _candle(t0 + timedelta(days=11), h=99.0, lo=97.0, c=98.0)
        tb.resolve_at_cursor(no_touch, max_hold_days=10)
        assert tb.has_no_open_trade is True
        closed = tb.trades[-1]
        assert closed.result == "cancelled"
        assert closed.pnl == 0.0
        assert closed.exit_reason is ExitReason.CANCEL

    def test_close_trade_passthrough_reason(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1) - timedelta(days=1)
        c = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0))
        close_ts = t0 + timedelta(days=2)
        tb.close_trade(112.0, close_ts, "", ExitReason.TARGET)
        closed = tb.trades[-1]
        assert closed.result == "win"
        assert closed.exit_reason is ExitReason.TARGET
        assert closed.exit_timestamp == close_ts

    def test_exit_reason_uniqueness(self) -> None:
        assert len({r.value for r in ExitReason}) == len(ExitReason)


class TestExcursionTracking:
    """MFE/MAE (backlog 098): favourable/adverse excursion is tracked from fill
    via the candles the strategy sees, stamped currency units with R multiples,
    and survives both scheduled closes and broker timeouts."""

    def _open_bullish(self, tb: TradeBook, t0: datetime) -> None:
        c = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.2)
        tb.submit_order(c, _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=110.0, lo=90.0, c=102.0))

    def test_fill_candle_sets_initial_excursion(self) -> None:
        tb = TradeBook()
        t0 = datetime(2024, 1, 1)
        self._open_bullish(tb, t0)
        # No close yet (fill alone records no outcome) — excursions surface at
        # closure: mfe=(110-100)*0.2=2.0, mae=(100-90)*0.2=2.0.
        tb.close_trade(112.0, t0 + timedelta(days=2), reason=ExitReason.TARGET)
        closed = tb.trades[-1]
        assert closed.mfe == pytest.approx(2.0)
        assert closed.mae == pytest.approx(2.0)

    def test_dip_then_rally_updates_excursion_and_r(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        self._open_bullish(tb, t0)
        # Quiet candle: excursion unchanged.
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=106.0, lo=97.0, c=101.0))
        # Rally candle hits target: mfe grows to (115-100)*0.2=3.0, mae pinned.
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=3), h=115.0, lo=100.0, c=113.0))
        closed = tb.trades[-1]
        assert closed.result == "win"
        assert closed.mfe == pytest.approx(3.0)
        assert closed.mae == pytest.approx(2.0)
        assert closed.mfe_r == pytest.approx(3.0)  # risk_amount = 5*0.2 = 1.0
        assert closed.mae_r == pytest.approx(2.0)

    def test_cancelled_open_trade_keeps_excursions(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        self._open_bullish(tb, t0)
        # Never hits stop/target before max_hold_days -> broker timeout.
        tb.resolve_at_cursor(
            _candle(t0 + timedelta(days=11), h=102.0, lo=99.0, c=100.0),
            max_hold_days=10,
        )
        closed = tb.trades[-1]
        assert closed.result == "cancelled"
        assert closed.exit_reason is ExitReason.TIMEOUT
        assert closed.mfe == pytest.approx(2.0)
        assert closed.mae == pytest.approx(2.0)

    def test_bearish_excursion_direction_flipped(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        c = _candidate(
            direction=TrendDirection.BEARISH,
            entry=100.0,
            stop=105.0,
            target=90.0,
            size=0.2,
        )
        tb.submit_order(c, _signal(TrendDirection.BEARISH), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=92.0, lo=88.0, c=90.0))
        # Short: fav = (entry - low); adv = (high - entry). Day 2 pierces the
        # target (low 86 <= 90): mfe=(100-86)*0.2=2.8, mae=(103-100)*0.2=0.6.
        tb.resolve_at_cursor(_candle(t0 + timedelta(days=2), h=103.0, lo=86.0, c=89.0))
        closed = tb.trades[-1]
        assert closed.result == "win"
        assert closed.pnl == pytest.approx(2.0)
        assert closed.mfe == pytest.approx(2.8)
        assert closed.mae == pytest.approx(0.6)
        assert closed.mfe_r == pytest.approx(2.8)
        assert closed.mae_r == pytest.approx(0.6)


class TestEquityCurve:
    """Time-indexed balance series: one (close_time, balance) point per real
    close, in order. Cancel/unrealized events contribute nothing."""

    def test_curve_captures_balance_after_each_close(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        tb.submit_order(
            _candidate(entry=100.0, stop=95.0, target=115.0, size=1.0),
            _signal(), "s", t0,
        )
        tb.fill_order(_candle(t0 + timedelta(days=1), h=112.0, lo=99.0))
        close_ts = t0 + timedelta(days=2)
        tb.close_trade(113.0, close_ts, reason=ExitReason.TARGET)
        curve = tb.equity_curve
        assert len(curve) == 1
        ts, balance = curve[0]
        assert ts == close_ts
        assert balance == pytest.approx(1000.0 + (113.0 - 100.0) * 1.0)

    def test_curve_multiple_closes_in_order(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        for i, target in enumerate((105.0, 110.0), start=1):
            c = _candidate(entry=100.0, stop=95.0, target=target, size=1.0)
            tb.submit_order(c, _signal(), "s", t0)
            tb.fill_order(_candle(t0 + timedelta(days=1), h=108.0, lo=98.0))
            tb.close_trade(target, t0 + timedelta(days=1 + i), reason=ExitReason.TARGET)
        curve = tb.equity_curve
        assert len(curve) == 2
        assert curve[0][1] == pytest.approx(1005.0)
        assert curve[1][1] == pytest.approx(1015.0)
        assert curve == tuple(sorted(curve, key=lambda pt: pt[0]))

    def test_filtered_by_instrument_rebuilds_curve(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        tb.submit_order(
            _candidate(entry=100.0, stop=95.0, target=115.0, size=1.0),
            _signal(), "s", t0, instrument="AAA",
        )
        tb.fill_order(_candle(t0 + timedelta(days=1), h=112.0, lo=99.0), instrument="AAA")
        tb.close_trade(113.0, t0 + timedelta(days=2), "AAA", ExitReason.TARGET)
        subset = tb.filtered_by_instrument("AAA")
        assert len(subset.trades) == 1
        assert len(subset.equity_curve) == 1
        assert subset.equity_curve[0][1] == pytest.approx(1000.0 + 13.0)


class TestTradeContextCapture:
    """Per-trade regime context (backlog 098): the dict passed at submit rides
    the order through fill and close, and survives timeout cancellation of an
    open trade (pending-never-filled carries nothing)."""

    def test_context_rides_submit_to_close(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        ctx = {"atr_pct": 1.5, "vol_ratio": 1.1, "rng20_atr": 4.0, "trend_eff": 0.4}
        tb.submit_order(_candidate(), _signal(), "s", t0, context=dict(ctx))
        tb.fill_order(_candle(t0 + timedelta(days=1), h=112.0, lo=99.0))
        tb.close_trade(113.0, t0 + timedelta(days=2), reason=ExitReason.TARGET)
        closed = tb.trades[-1]
        assert closed.context == ctx

    def test_context_default_none(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        tb.submit_order(_candidate(), _signal(), "s", t0)
        tb.fill_order(_candle(t0 + timedelta(days=1), h=112.0, lo=99.0))
        tb.close_trade(113.0, t0 + timedelta(days=2), reason=ExitReason.TARGET)
        assert tb.trades[-1].context is None

    def test_context_survives_open_timeout_cancel(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        t0 = datetime(2024, 1, 1)
        ctx = {"trend_eff": -0.2}
        tb.submit_order(_candidate(), _signal(), "s", t0, context=dict(ctx))
        tb.fill_order(_candle(t0 + timedelta(days=1), h=103.0, lo=99.0))
        tb.resolve_at_cursor(
            _candle(t0 + timedelta(days=11), h=102.0, lo=99.0, c=100.0),
            max_hold_days=10,
        )
        closed = tb.trades[-1]
        assert closed.exit_reason is ExitReason.TIMEOUT
        assert closed.context == ctx
