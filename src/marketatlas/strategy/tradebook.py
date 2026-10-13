from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast

from marketatlas.data.types import Candle
from marketatlas.facts.structural import TrendDirection
from marketatlas.strategy.ledger import TradeLedger
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.trade import ExitPlan, ExitReason, TradeCandidate


@dataclass(frozen=True)
class _PendingOrder:
    candidate: TradeCandidate
    signal: TradeSignal
    source: str
    instrument: str
    timestamp: datetime
    context: dict[str, float] | None = None


@dataclass
class _ExitState:
    """Mutable open-position bookkeeping for one live trade.

    Owns the scaled-out size, banked P&L, runner stop geometry, and the
    observed favourable/adverse excursion (MFE/MAE) while the position is
    live. The frozen ``TradeCandidate``/``TradeOutcome`` records keep the
    reported math pure; this object is created for every filled trade (plan
    stays None when no ``ExitPlan`` is active).
    """

    plan: ExitPlan | None = None
    scaled_out: bool = False
    remaining_fraction: float = 1.0
    realized_pnl: float = 0.0
    breakeven_active: bool = False
    trail_stop: float | None = None
    runner_target: float | None = None
    extreme: float = 0.0
    mfe: float = 0.0  # max favourable excursion, account currency (orig size)
    mae: float = 0.0  # max adverse excursion, account currency (orig size)


@dataclass(frozen=True)
class TradeOutcome:
    submit_time: datetime
    entry_timestamp: datetime
    exit_timestamp: datetime | None
    candidate: TradeCandidate
    signal: TradeSignal
    source_strategy: str
    instrument: str
    pnl: float | None
    result: str | None  # "win" / "loss" / "breakeven" / "cancelled" / None
    exit_reason: ExitReason | None = None
    # Favourable/adverse excursion while open, in account currency (computed
    # over the ORIGINAL position size, so R-units stay comparable across
    # scaled-out trades) and in R units (excursion / candidate.risk_amount).
    mfe: float | None = None
    mae: float | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    # Trade-entry regime context (atr_pct, vol_ratio, trend_eff, rng20_atr,
    # ...) captured at the signal candle, for post-hoc regime-gate research.
    context: dict[str, float] | None = None


class TradeBook:
    """Trade lifecycle + reporting facade over a shared ``TradeLedger``.

    Owns order state (pending/open/closed per instrument lane) and the
    position lifecycle — submit → fill → close/cancel. Equity accounting (the
    compounding cash balance, peak, total P&L, drawdown) is delegated to a
    ``TradeLedger``; win/loss aggregation and monthly breakdowns are pure reads
    over the closed trades. No position math lives here.
    """

    def __init__(self, initial_balance: float = 1000.0) -> None:
        self._ledger = TradeLedger(initial_balance)
        self._trades: list[TradeOutcome] = []
        self._open_trades: dict[str, TradeOutcome] = {}
        self._pending: dict[str, _PendingOrder] = {}
        self._exit_states: dict[str, _ExitState] = {}

    @property
    def balance(self) -> float:
        return self._ledger.balance

    @property
    def initial_balance(self) -> float:
        return self._ledger.initial_balance

    @property
    def peak_balance(self) -> float:
        return self._ledger.peak_balance

    @property
    def trades(self) -> tuple[TradeOutcome, ...]:
        return tuple(self._trades)

    @property
    def equity_curve(self) -> tuple[tuple[datetime, float], ...]:
        """Time-indexed balance series (close time, balance after close)."""
        return self._ledger.equity_curve

    @property
    def win_count(self) -> int:
        return sum(1 for t in self._trades if t.result == "win")

    @property
    def loss_count(self) -> int:
        return sum(1 for t in self._trades if t.result == "loss")

    @property
    def breakeven_count(self) -> int:
        return sum(1 for t in self._trades if t.result == "breakeven")

    @property
    def closed_count(self) -> int:
        return len(self._trades)

    @property
    def win_rate(self) -> float:
        total = self.win_count + self.loss_count
        if total == 0:
            return 0.0
        return self.win_count / total

    @property
    def total_pnl(self) -> float:
        return self._ledger.total_pnl

    @property
    def gross_profit(self) -> float:
        return sum(float(t.pnl) for t in self._trades if t.pnl is not None and t.pnl > 0)

    @property
    def gross_loss(self) -> float:
        return abs(sum(float(t.pnl) for t in self._trades if t.pnl is not None and t.pnl < 0))

    @property
    def profit_factor(self) -> float:
        if self.gross_loss == 0:
            return float("inf") if self.gross_profit > 0 else 0.0
        return self.gross_profit / self.gross_loss

    @property
    def avg_win(self) -> float:
        wins = [t.pnl for t in self._trades if t.result == "win" and t.pnl is not None]
        return sum(wins) / len(wins) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t.pnl for t in self._trades if t.result == "loss" and t.pnl is not None]
        return sum(losses) / len(losses) if losses else 0.0

    @property
    def expectancy(self) -> float:
        total = self.win_count + self.loss_count
        if total == 0:
            return 0.0
        return self.total_pnl / total

    # --- R-based metrics (backlog: growth measurement) -----------------------
    # R = one unit of risk. Each trade's outcome expressed in R multiplies
    # pnl / risk_amount, so edge, payoff and Kelly are comparable across
    # instruments/setups regardless of nominal price or size.

    @staticmethod
    def _r_for(trade: TradeOutcome) -> float | None:
        c = trade.candidate
        if trade.pnl is None or not c.risk_amount:
            return None
        return float(trade.pnl) / c.risk_amount

    @property
    def avg_win_r(self) -> float:
        values = [
            r
            for t in self._trades
            if t.result == "win" and (r := self._r_for(t)) is not None
        ]
        return sum(values) / len(values) if values else 0.0

    @property
    def avg_loss_r(self) -> float:
        """Average loss magnitude in R units (positive; payoff ratios stay sane)."""
        values = [
            r
            for t in self._trades
            if t.result == "loss" and (r := self._r_for(t)) is not None
        ]
        return sum(abs(v) for v in values) / len(values) if values else 0.0

    @property
    def payoff_ratio(self) -> float:
        """Avg win (R) / avg loss (R); NaN-safe ``0.0`` when no losses.

        ``inf`` is returned when losses exist but wins don't (pure losing), or
        when the strategy has wins and no losses (pure winning, ``inf``).
        """
        aw = self.avg_win_r
        al = self.avg_loss_r
        if al == 0:
            return float("inf") if aw > 0 else 0.0
        return aw / al

    @property
    def expectancy_in_r(self) -> float:
        """Edge per trade in R units: (w * avg_win_R) - (l * avg_loss_R)."""
        w = self.win_rate
        l = 1.0 - w
        return w * self.avg_win_r - l * self.avg_loss_r

    @property
    def kelly_fraction(self) -> float:
        """Full Kelly for win-rate/payoff pair, clamped to [0, 1).

        Full Kelly on a decided-trades basis. Real deployment would use a
        fraction of this (half-Kelly typical). ``0.0`` when no edge.
        """
        w = self.win_rate
        if w <= 0 or w >= 1:
            return 0.0
        aw = self.avg_win_r
        al = self.avg_loss_r
        if aw <= 0 or al <= 0:
            return 0.0
        # Kelly: f* = (W - L / b) where b = win payoff per unit risk (avg_win_R),
        # L = loss per unit risk (avg_loss_R). With symmetric stop sizing
        # avg_loss_R ~ 1.0. Clamp against degenerate payoff.
        return max(0.0, min(1.0 - 1e-9, w - (1.0 - w) * al / aw))

    @property
    def trades_per_year(self) -> float:
        """Decided (closed) trades normalized over the run's calendar span.

        Span is first submit to last exit; collapses to ``0.0`` for <2 timestamps.
        """
        stamps = [
            t.exit_timestamp or t.entry_timestamp
            for t in self._trades
            if t.exit_timestamp is not None or t.entry_timestamp is not None
        ]
        if len(stamps) < 2:
            return 0.0
        days = (max(stamps) - min(stamps)).total_seconds() / 86400.0
        if days <= 0:
            return 0.0
        return self.closed_count / (days / 365.25)

    @property
    def by_direction(self) -> dict[str, dict[str, object]]:
        """Per-direction decided stats: trades, wins, losses, win_rate."""
        out: dict[str, dict[str, object]] = {}
        for trade in self._trades:
            if trade.result not in ("win", "loss"):
                continue
            name = trade.candidate.direction.value
            row = out.setdefault(
                name, {"trades": 0, "wins": 0, "losses": 0, "gross_pnl": 0.0}
            )
            trades: int = int(cast(int, row["trades"]))
            wins: int = int(cast(int, row["wins"]))
            losses: int = int(cast(int, row["losses"]))
            pnl: float = float(cast(float, row["gross_pnl"]))
            row["trades"] = trades + 1
            if trade.result == "win":
                row["wins"] = wins + 1
            else:
                row["losses"] = losses + 1
            if trade.pnl is not None:
                row["gross_pnl"] = pnl + trade.pnl
        for row in out.values():
            wins = int(cast(int, row["wins"]))
            losses = int(cast(int, row["losses"]))
            decided = wins + losses
            row["win_rate"] = wins / decided if decided else 0.0
        return out

    @property
    def max_drawdown(self) -> float:
        pnls = tuple(float(t.pnl) for t in self._trades if t.pnl is not None)
        return TradeLedger.max_drawdown(pnls, self._ledger.initial_balance)

    @property
    def has_no_open_trade(self) -> bool:
        return not self._open_trades

    @property
    def has_pending_order(self) -> bool:
        return bool(self._pending)

    @property
    def open_instruments(self) -> tuple[str, ...]:
        return tuple(self._open_trades)

    @property
    def busy_instruments(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*self._open_trades, *self._pending]))

    def lane_has_open(self, instrument: str) -> bool:
        return instrument in self._open_trades

    def lane_has_pending(self, instrument: str) -> bool:
        return instrument in self._pending

    def lane_busy(self, instrument: str) -> bool:
        return instrument in self._open_trades or instrument in self._pending

    def pending_ts(self, instrument: str) -> datetime | None:
        pending = self._pending.get(instrument)
        return pending.timestamp if pending is not None else None

    def _update_excursion(self, candle: Candle, st: _ExitState, c: TradeCandidate) -> None:
        """Track max favourable/adverse excursion of the open position.

        Uses the candle the strategy actually sees (same candle visibility as
        stop/target resolution — no lookahead). Excursion is measured against
        the ORIGINAL position size so ``mfe_r``/``mae_r`` stay comparable
        across scale-out trades; ``candle.high/low`` are the realistic intraday
        extremes for a position filled at ``c.entry``.
        """
        if c.direction == TrendDirection.BULLISH:
            fav = (candle.high - c.entry) * c.size
            adv = (c.entry - candle.low) * c.size
        else:
            fav = (c.entry - candle.low) * c.size
            adv = (candle.high - c.entry) * c.size
        if fav > st.mfe:
            st.mfe = fav
        if adv > st.mae:
            st.mae = adv

    def submit_order(
        self,
        candidate: TradeCandidate,
        signal: TradeSignal,
        source: str,
        signal_timestamp: datetime,
        instrument: str = "",
        context: dict[str, float] | None = None,
    ) -> None:
        self._pending[instrument] = _PendingOrder(
            candidate=candidate,
            signal=signal,
            source=source,
            instrument=instrument,
            timestamp=signal_timestamp,
            context=context,
        )

    def fill_order(self, candle: Candle, instrument: str = "") -> None:
        """Fill a pending order.

        Two execution models, selected by ``TradeCandidate.entry_at_open``:

        * ``touch`` (default): the order fills once the candle trades through
          the submitted entry (bullish: ``candle.high >= entry``; bearish:
          ``candle.low <= entry``). Until price crosses the entry the order
          stays pending — a gap that never returns to the entry never fills.
          The fill price is the submitted entry; stop/target/size/risk are
          untouched.
        * ``at_open`` (EOD → next-open workflow): the broker processes the
          post-close order at the next market open, so the order fills at the
          next candle's ``open`` (with slippage). A ``max_open_gap`` band
          rejected the open outright (skips the trade); otherwise the
          candidate is re-anchored at the open so the swing-anchored stop and
          fixed $ risk are preserved, and an open already past the stop or
          target closes immediately at that open.
        """
        pending = self._pending.get(instrument)
        if pending is None or pending.candidate is None:
            return
        candidate = pending.candidate
        if pending.signal is None:
            return
        if candidate.entry_at_open:
            self._fill_at_open(candle, instrument, pending)
            return
        if candidate.direction == TrendDirection.BULLISH:
            if candle.high < candidate.entry:
                return
        else:
            if candle.low > candidate.entry:
                return
        self._open_trades[instrument] = TradeOutcome(
            submit_time=pending.timestamp or candle.timestamp,
            entry_timestamp=candle.timestamp,
            exit_timestamp=None,
            candidate=candidate,
            signal=pending.signal,
            source_strategy=pending.source,
            instrument=pending.instrument,
            pnl=None,
            result=None,
            context=pending.context,
        )
        plan = (
            candidate.exit_plan
            if candidate.exit_plan is not None and candidate.exit_plan.enabled
            else None
        )
        self._exit_states[instrument] = _ExitState(plan=plan)
        self._update_excursion(candle, self._exit_states[instrument], candidate)
        del self._pending[instrument]

    def _fill_at_open(
        self, candle: Candle, instrument: str, pending: _PendingOrder
    ) -> None:
        """Fill an ``at_open`` pending order at the next candle's open.

        EOD workflow: the order was submitted after candle close and the broker
        processes it at the next market open, so the fill price is the next
        candle's ``open`` (plus slippage against the entry direction). The
        order is declined (recorded as a cancel) when the open falls outside
        the approved geometry — a ``max_open_gap`` band against the signal
        close skipped the trade outright, or the open gapped through the stop
        or target (no position exists pre-open, so there is nothing to stop
        out — the entry itself was invalid). Otherwise the candidate is
        re-anchored at the open — swing-anchored stop and fixed $ risk are
        preserved — and the bar's own intraday range resolves stop/target.
        """
        candidate = pending.candidate
        if (
            candidate.max_open_gap > 0
            and candidate.reference_price is not None
            and abs(candle.open - candidate.reference_price) > candidate.max_open_gap
        ):
            self._cancel_pending(candle, instrument)
            return
        slip = candidate.slippage_pct / 100
        raw_open = candle.open
        if candidate.direction == TrendDirection.BULLISH:
            open_fill = raw_open * (1 + slip)
            crossed = open_fill <= candidate.stop or open_fill >= candidate.target
        else:
            open_fill = raw_open * (1 - slip)
            crossed = open_fill >= candidate.stop or open_fill <= candidate.target
        if crossed:
            # Open beyond stop/target = the intended entry never existed.
            self._cancel_pending(candle, instrument)
            return
        c = self._reanchor_at_open(candidate, open_fill)
        self._open_trades[instrument] = TradeOutcome(
            submit_time=pending.timestamp or candle.timestamp,
            entry_timestamp=candle.timestamp,
            exit_timestamp=None,
            candidate=c,
            signal=pending.signal,
            source_strategy=pending.source,
            instrument=pending.instrument,
            pnl=None,
            result=None,
            context=pending.context,
        )
        plan = (
            c.exit_plan
            if c.exit_plan is not None and c.exit_plan.enabled
            else None
        )
        self._exit_states[instrument] = _ExitState(plan=plan)
        self._update_excursion(candle, self._exit_states[instrument], c)
        del self._pending[instrument]

    @staticmethod
    def _reanchor_at_open(candidate: TradeCandidate, open_fill: float) -> TradeCandidate:
        """Re-base a touched-candidate's geometry at the realized open fill.

        Keeps the swing-anchored stop level, the submitted RR, and the fixed $
        risk amount; recomputes size/target from the actual open so an open
        drift does not silently change the risk/reward the trade was approved
        with. A gap in the open's favour narrows the stop distance and grows
        the size; a gap against widens the stop distance and shrinks it —
        either way one unit of risk stays the risk envelope.
        """
        stop_distance = abs(open_fill - candidate.stop)
        if stop_distance <= 0 or candidate.risk_amount <= 0:
            return candidate
        size = candidate.risk_amount / stop_distance
        rr = candidate.rr_ratio if candidate.rr_ratio > 0 else 1.0
        if candidate.direction == TrendDirection.BULLISH:
            target = open_fill + rr * stop_distance
        else:
            target = open_fill - rr * stop_distance
        return replace(
            candidate,
            entry=open_fill,
            target=target,
            size=size,
            reward_amount=rr * candidate.risk_amount,
        )

    def close_trade(
        self,
        exit_price: float,
        timestamp: datetime,
        instrument: str = "",
        reason: ExitReason | None = None,
    ) -> None:
        trade = self._open_trades.get(instrument)
        if trade is None:
            return
        c = trade.candidate
        st = self._exit_states.get(instrument)
        size = c.size * (st.remaining_fraction if st is not None else 1.0)
        if c.direction == TrendDirection.BULLISH:
            pnl = (exit_price - c.entry) * size
        else:
            pnl = (c.entry - exit_price) * size
        if st is not None:
            pnl += st.realized_pnl

        if pnl > 0:
            result = "win"
        elif pnl < 0:
            result = "loss"
        else:
            result = "breakeven"

        closed = TradeOutcome(
            submit_time=trade.submit_time,
            entry_timestamp=trade.entry_timestamp,
            exit_timestamp=timestamp,
            candidate=c,
            signal=trade.signal,
            source_strategy=trade.source_strategy,
            instrument=trade.instrument,
            pnl=pnl,
            result=result,
            exit_reason=reason,
            mfe=st.mfe if st is not None else None,
            mae=st.mae if st is not None else None,
            mfe_r=((st.mfe / c.risk_amount) if st is not None and c.risk_amount else None),
            mae_r=((st.mae / c.risk_amount) if st is not None and c.risk_amount else None),
            context=trade.context,
        )
        self._trades.append(closed)
        self._ledger.apply(pnl, timestamp)
        self._exit_states.pop(instrument, None)
        del self._open_trades[instrument]

    def resolve_at_cursor(
        self, candle: Candle, max_hold_days: int = 10, instrument: str = ""
    ) -> None:
        pending = self._pending.get(instrument)
        if pending is not None and pending.timestamp is not None:
            pending_days = (candle.timestamp - pending.timestamp).days
            if pending_days >= max_hold_days:
                self._cancel_pending(candle, instrument)
        open_trade = self._open_trades.get(instrument)
        if open_trade is None:
            return
        c = open_trade.candidate
        st = self._exit_states.get(instrument)
        assert st is not None  # every filled trade carries an _ExitState
        plan = st.plan

        self._update_excursion(candle, st, c)

        if plan is not None:
            assert st is not None
            if plan.scale_out_fraction > 0:
                self._resolve_scaled(candle, open_trade, st)
            elif plan.breakeven_at_rr > 0:
                self._resolve_ratchet(candle, open_trade, st, plan)
            if instrument not in self._open_trades:
                return
        else:
            # Stop/target are checked before the max-hold expiry below so a
            # trade that touches either on the boundary candle realizes that
            # outcome instead of being cancelled at pnl 0 (backlog 104 —
            # AUDJPY 2026-01-29 hit target on day 10 but was recorded
            # cancelled).
            if c.direction == TrendDirection.BULLISH:
                if candle.low <= c.stop:
                    self.close_trade(c.stop, candle.timestamp, instrument, ExitReason.STOP)
                    return
                if candle.high >= c.target:
                    self.close_trade(c.target, candle.timestamp, instrument, ExitReason.TARGET)
                    return
            else:
                if candle.high >= c.stop:
                    self.close_trade(c.stop, candle.timestamp, instrument, ExitReason.STOP)
                    return
                if candle.low <= c.target:
                    self.close_trade(c.target, candle.timestamp, instrument, ExitReason.TARGET)
                    return

        days_held = (candle.timestamp - open_trade.entry_timestamp).days
        if days_held >= max_hold_days:
            # Max-hold is a strategy rule, not a broker feature: the strategy
            # closes the live position at market, so the exit realizes the
            # candle's price. A synthetic pnl-0 cancel would discard both gains
            # and losses and was never realistic (nor consistent with the
            # scaled-out branch below, which always closed at market).
            self.close_trade(candle.close, candle.timestamp, instrument, ExitReason.TIMEOUT)

    def _resolve_ratchet(
        self, candle: Candle, trade: TradeOutcome, st: _ExitState, plan: ExitPlan
    ) -> None:
        """Resolve a breakeven-ratchet carry (no partial fills).

        While unarmed the original stop plus the submitted target govern.
        Once price trades through ``breakeven_at_rr`` of the original stop
        distance, the stop ratchets to entry — a stop-modification order, not
        a position split. Any later adverse retracement exits at breakeven
        (~0R) instead of the original -1R stop.
        """
        c = trade.candidate
        bull = c.direction == TrendDirection.BULLISH
        stop_distance = abs(c.entry - c.stop)
        active_stop = c.entry if st.breakeven_active else c.stop
        if (bull and candle.low <= active_stop) or (not bull and candle.high >= active_stop):
            self.close_trade(active_stop, candle.timestamp, trade.instrument, ExitReason.STOP)
            return
        if not st.breakeven_active:
            if bull:
                armed = candle.high >= c.entry + plan.breakeven_at_rr * stop_distance
            else:
                armed = candle.low <= c.entry - plan.breakeven_at_rr * stop_distance
            if armed:
                st.breakeven_active = True
        if (bull and candle.high >= c.target) or (not bull and candle.low <= c.target):
            self.close_trade(c.target, candle.timestamp, trade.instrument, ExitReason.TARGET)

    def _resolve_scaled(
        self, candle: Candle, trade: TradeOutcome, st: _ExitState
    ) -> None:
        """Resolve a carry that has an enabled ExitPlan.

        Pre-scale: the original stop governs; once price reaches the scale-R
        level the plan banks a fraction, moves the remainder to a breakeven/
        trailing stop, and lets it chase the runner target. A price level is
        scaled only from the first touch (R in units of the original stop
        distance); later touches on later trades re-scale independently.
        """
        assert st.plan is not None
        c = trade.candidate
        bull = c.direction == TrendDirection.BULLISH
        stop_distance = abs(c.entry - c.stop)

        if not st.scaled_out:
            if (bull and candle.low <= c.stop) or (not bull and candle.high >= c.stop):
                self.close_trade(c.stop, candle.timestamp, trade.instrument, ExitReason.STOP)
                return
            scale_price = (
                c.entry + st.plan.scale_out_rr * stop_distance
                if bull
                else c.entry - st.plan.scale_out_rr * stop_distance
            )
            triggered = (bull and candle.high >= scale_price) or (
                not bull and candle.low <= scale_price
            )
            if not triggered:
                return
            self._apply_scale_out(trade.instrument, scale_price, st)

        self._update_trail(candle, st, bull, stop_distance)
        runner_stop = self._runner_stop_price(c, st, bull)
        if runner_stop is not None:
            if (bull and candle.low <= runner_stop) or (
                not bull and candle.high >= runner_stop
            ):
                self.close_trade(
                    runner_stop, candle.timestamp, trade.instrument, ExitReason.STOP
                )
                return
        if st.runner_target is not None:
            if (bull and candle.high >= st.runner_target) or (
                not bull and candle.low <= st.runner_target
            ):
                self.close_trade(
                    st.runner_target, candle.timestamp, trade.instrument, ExitReason.TARGET
                )
                return

    def _apply_scale_out(
        self, instrument: str, scale_price: float, st: _ExitState
    ) -> None:
        """Bank a fraction of the position at ``scale_price`` and arm runner exits."""
        assert st.plan is not None
        trade = self._open_trades[instrument]
        c = trade.candidate
        bull = c.direction == TrendDirection.BULLISH
        banked = (
            (scale_price - c.entry) if bull else (c.entry - scale_price)
        ) * c.size * st.plan.scale_out_fraction
        st.realized_pnl = banked
        st.remaining_fraction = 1.0 - st.plan.scale_out_fraction
        st.scaled_out = True
        stop_distance = abs(c.entry - c.stop)
        if st.plan.breakeven_after_scale:
            st.breakeven_active = True
        if st.plan.trailing_stop_rr > 0:
            st.extreme = scale_price
            st.trail_stop = (
                scale_price - st.plan.trailing_stop_rr * stop_distance
                if bull
                else scale_price + st.plan.trailing_stop_rr * stop_distance
            )
        if st.plan.runner_target_rr > 0:
            st.runner_target = (
                c.entry + st.plan.runner_target_rr * stop_distance
                if bull
                else c.entry - st.plan.runner_target_rr * stop_distance
            )

    def _update_trail(
        self, candle: Candle, st: _ExitState, bull: bool, stop_distance: float
    ) -> None:
        """Ratchet the trailing stop against the newest runner extreme."""
        if st.plan is None or st.plan.trailing_stop_rr <= 0:
            return
        extreme = max(st.extreme, candle.high) if bull else min(st.extreme, candle.low)
        st.extreme = extreme
        new_stop = (
            extreme - st.plan.trailing_stop_rr * stop_distance
            if bull
            else extreme + st.plan.trailing_stop_rr * stop_distance
        )
        if bull:
            if st.trail_stop is None or new_stop > st.trail_stop:
                st.trail_stop = new_stop
        else:
            if st.trail_stop is None or new_stop < st.trail_stop:
                st.trail_stop = new_stop

    def _runner_stop_price(
        self, c: TradeCandidate, st: _ExitState, bull: bool
    ) -> float | None:
        """Active runner stop: trailing (tightest) else breakeven else None."""
        if st.trail_stop is not None:
            if st.breakeven_active:
                be = c.entry
                return max(be, st.trail_stop) if bull else min(be, st.trail_stop)
            return st.trail_stop
        if st.breakeven_active:
            return c.entry
        return None

    def _cancel_pending(self, candle: Candle, instrument: str = "") -> None:
        """Drop a pending order that never reached its entry within max_hold_days.

        Records the cancellation so the rejected order is visible and frees the
        book to consider later signals.
        """
        pending = self._pending.get(instrument)
        if pending is None:
            return
        cancelled = TradeOutcome(
            submit_time=pending.timestamp or candle.timestamp,
            entry_timestamp=pending.timestamp or candle.timestamp,
            exit_timestamp=candle.timestamp,
            candidate=pending.candidate,
            signal=pending.signal,
            source_strategy=pending.source,
            instrument=pending.instrument,
            pnl=0.0,
            result="cancelled",
            exit_reason=ExitReason.CANCEL,
        )
        self._trades.append(cancelled)
        del self._pending[instrument]

    def filtered_by_instrument(self, canonical: str) -> TradeBook:
        """A copy of the book holding only ``canonical``'s closed trades.

        The shared book is untouched; balance, peak, and drawdown are recomputed
        from the subset so per-instrument charts and summaries stay internally
        consistent (backlog 077).
        """
        book = TradeBook(self._ledger.initial_balance)
        subset = [t for t in self._trades if t.instrument == canonical]
        book._trades = subset
        for trade in subset:
            if trade.pnl is not None:
                book._ledger.apply(trade.pnl, trade.exit_timestamp)
        return book

    @property
    def summary(self) -> dict[str, object]:
        return {
            "initial_balance": self.initial_balance,
            "final_balance": self.balance,
            "total_pnl": self.total_pnl,
            "total_return_pct": (
                (self.total_pnl / self.initial_balance) * 100 if self.initial_balance != 0 else 0.0
            ),
            "total_trades": self.closed_count,
            "wins": self.win_count,
            "losses": self.loss_count,
            "breakevens": self.breakeven_count,
            "win_rate": self.win_rate,
            "peak_balance": self.peak_balance,
            "max_drawdown": self.max_drawdown,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "profit_factor": self.profit_factor,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "expectancy": self.expectancy,
            "avg_win_r": self.avg_win_r,
            "avg_loss_r": self.avg_loss_r,
            "payoff_ratio": self.payoff_ratio,
            "expectancy_in_r": self.expectancy_in_r,
            "kelly_fraction": self.kelly_fraction,
            "trades_per_year": self.trades_per_year,
            "by_direction": self.by_direction,
            "by_strategy": self._strategy_breakdown(),
            "by_instrument": self._instrument_breakdown(),
        }

    def monthly_summary(self) -> dict[str, dict[str, object]]:
        """Closed trades grouped by exit month (``YYYY-MM``), sorted chronologically.

        Every month from the first to the last trade is present, including months
        with no closed trades (zero-filled). Each month carries ``growth_pct`` —
        the fund's realized growth for that month, computed from the running
        balance change driven by that month's closes, so percentages compound
        across the span.
        """
        months: dict[str, dict[str, object]] = {}
        for trade in self._trades:
            timestamp = trade.exit_timestamp or trade.entry_timestamp
            key = timestamp.strftime("%Y-%m")
            if key not in months:
                months[key] = {
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "breakevens": 0,
                    "total_pnl": 0.0,
                }
            row = months[key]
            row["trades"] = row["trades"] + 1  # type: ignore[operator]
            if trade.result == "win":
                row["wins"] = row["wins"] + 1  # type: ignore[operator]
            elif trade.result == "loss":
                row["losses"] = row["losses"] + 1  # type: ignore[operator]
            elif trade.result == "breakeven":
                row["breakevens"] = row["breakevens"] + 1  # type: ignore[operator]
            if trade.pnl is not None:
                row["total_pnl"] = row["total_pnl"] + trade.pnl  # type: ignore[operator]
        if not months:
            return {}
        keys = sorted(months)
        cursor = datetime.strptime(keys[0], "%Y-%m").replace(day=1)
        end = datetime.strptime(keys[-1], "%Y-%m").replace(day=1)
        balance = self._ledger.initial_balance
        result: dict[str, dict[str, object]] = {}
        while cursor <= end:
            key = cursor.strftime("%Y-%m")
            row = months.get(
                key,
                {
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "breakevens": 0,
                    "total_pnl": 0.0,
                },
            )
            start_balance = balance
            balance += float(row["total_pnl"])  # type: ignore[arg-type]
            row["growth_pct"] = (
                (balance - start_balance) / start_balance * 100
                if start_balance != 0
                else 0.0
            )
            result[key] = row
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)
        return result

    def _instrument_breakdown(self) -> dict[str, dict[str, object]]:
        return self._breakdown_by("instrument")

    def _strategy_breakdown(self) -> dict[str, dict[str, object]]:
        return self._breakdown_by("source_strategy")

    def _breakdown_by(self, key: str) -> dict[str, dict[str, object]]:
        breakdown: dict[str, dict[str, object]] = {}
        for trade in self._trades:
            name = getattr(trade, key)
            if name not in breakdown:
                breakdown[name] = {
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "breakevens": 0,
                    "gross_profit": 0.0,
                    "gross_loss": 0.0,
                    "total_pnl": 0.0,
                }
            entry = breakdown[name]
            entry["trades"] = entry["trades"] + 1  # type: ignore[operator]
            if trade.result == "win":
                entry["wins"] = entry["wins"] + 1  # type: ignore[operator]
            elif trade.result == "loss":
                entry["losses"] = entry["losses"] + 1  # type: ignore[operator]
            elif trade.result == "breakeven":
                entry["breakevens"] = entry["breakevens"] + 1  # type: ignore[operator]
            if trade.pnl is not None:
                entry["total_pnl"] = entry["total_pnl"] + trade.pnl  # type: ignore[operator]
                if trade.pnl > 0:
                    entry["gross_profit"] = entry["gross_profit"] + trade.pnl  # type: ignore[operator]
                elif trade.pnl < 0:
                    entry["gross_loss"] = entry["gross_loss"] + abs(trade.pnl)  # type: ignore[operator]
        for entry in breakdown.values():
            wins = int(entry["wins"])  # type: ignore[call-overload]
            losses = int(entry["losses"])  # type: ignore[call-overload]
            decided = wins + losses
            gross_profit = float(entry["gross_profit"])  # type: ignore[arg-type]
            gross_loss = float(entry["gross_loss"])  # type: ignore[arg-type]
            entry["win_rate"] = wins / decided if decided else 0.0
            entry["profit_factor"] = (
                float("inf")
                if gross_loss == 0 and gross_profit > 0
                else (0.0 if gross_loss == 0 else gross_profit / gross_loss)
            )
        return breakdown
