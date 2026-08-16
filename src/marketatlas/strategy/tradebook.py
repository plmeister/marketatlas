from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from marketatlas.data.types import Candle
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.structural import TrendDirection
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.trade import TradeCandidate


@dataclass(frozen=True)
class TradeOutcome:
    entry_timestamp: datetime
    exit_timestamp: datetime | None
    candidate: TradeCandidate
    signal: TradeSignal
    source_strategy: str
    instrument: str
    pnl: float | None
    result: str | None  # "win" / "loss" / "breakeven" / None


class TradeBook:
    def __init__(self, initial_balance: float = 1000.0) -> None:
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._trades: list[TradeOutcome] = []
        self._open_trade: TradeOutcome | None = None
        self._pending_order: TradeCandidate | None = None
        self._pending_signal: TradeSignal | None = None
        self._pending_source: str = ""
        self._pending_instrument: str = ""
        self._pending_timestamp: datetime | None = None
        self._peak_balance = initial_balance

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def initial_balance(self) -> float:
        return self._initial_balance

    @property
    def trades(self) -> tuple[TradeOutcome, ...]:
        return tuple(self._trades)

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
        return self._balance - self._initial_balance

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

    @property
    def max_drawdown(self) -> float:
        if not self._trades:
            return 0.0
        peak = self._initial_balance
        worst = 0.0
        bal = self._initial_balance
        for trade in self._trades:
            if trade.pnl is not None:
                bal += trade.pnl
            if bal > peak:
                peak = bal
            drawdown = (peak - bal) / peak if peak > 0 else 0.0
            if drawdown > worst:
                worst = drawdown
        return worst

    @property
    def peak_balance(self) -> float:
        return self._peak_balance

    @property
    def has_no_open_trade(self) -> bool:
        return self._open_trade is None

    @property
    def has_pending_order(self) -> bool:
        return self._pending_order is not None

    def submit_order(
        self,
        candidate: TradeCandidate,
        signal: TradeSignal,
        source: str,
        signal_timestamp: datetime,
        instrument: str = "",
    ) -> None:
        self._pending_order = candidate
        self._pending_signal = signal
        self._pending_source = source
        self._pending_instrument = instrument
        self._pending_timestamp = signal_timestamp

    def fill_order(self, open_price: float, timestamp: datetime) -> None:
        if self._pending_order is None:
            return
        candidate = self._pending_order
        signal = self._pending_signal
        source = self._pending_source
        instrument = self._pending_instrument
        if candidate is None or signal is None:
            return
        filled = self._reprice_at_fill(candidate, open_price)
        if filled is None:
            self._pending_order = None
            self._pending_signal = None
            self._pending_source = ""
            self._pending_instrument = ""
            self._pending_timestamp = None
            return
        self._open_trade = TradeOutcome(
            entry_timestamp=timestamp,
            exit_timestamp=None,
            candidate=filled,
            signal=signal,
            source_strategy=source,
            instrument=instrument,
            pnl=None,
            result=None,
        )
        self._pending_order = None
        self._pending_signal = None
        self._pending_source = ""
        self._pending_instrument = ""
        self._pending_timestamp = None

    @staticmethod
    def _reprice_at_fill(
        candidate: TradeCandidate, fill_price: float
    ) -> TradeCandidate | None:
        """Rebase a pending candidate onto its actual fill price.

        The order fills at the next candle's open while the planned entry was
        derived from the signal candle's open, so using the planned entry
        would pair an entry price from one date with an entry timestamp from
        another. Re-pricing here keeps both on the same candle, re-sizes to
        hold the planned dollar risk fixed, and cancels the order when the
        move between the signal open and the fill open pushes the actual
        reward/risk below the planned minimum.
        """
        if candidate.direction == TrendDirection.BULLISH:
            entry = fill_price * (1 + candidate.slippage_pct / 100)
        else:
            entry = fill_price * (1 - candidate.slippage_pct / 100)

        stop_distance = abs(entry - candidate.stop)
        if stop_distance <= 0:
            return None

        distance = abs(candidate.target - entry)
        rr_ratio = distance / stop_distance
        if candidate.min_rr > 0 and rr_ratio < candidate.min_rr:
            return None

        size = candidate.risk_amount / stop_distance
        note = (
            f"Filled at {entry:.2f} (open {fill_price:.2f}); "
            f"re-sized {size:.4f} to hold fixed risk"
        )
        return replace(
            candidate,
            entry=entry,
            size=size,
            rr_ratio=rr_ratio,
            reward_amount=size * distance,
            evidence=candidate.evidence
            + (EvidenceEntry(text=note, level=EvidenceLevel.INFO, source="TradeBook"),),
        )

    def close_trade(self, exit_price: float, timestamp: datetime) -> None:
        if self._open_trade is None:
            return
        trade = self._open_trade
        c = trade.candidate
        if c.direction == TrendDirection.BULLISH:
            pnl = (exit_price - c.entry) * c.size
        else:
            pnl = (c.entry - exit_price) * c.size

        if pnl > 0:
            result = "win"
        elif pnl < 0:
            result = "loss"
        else:
            result = "breakeven"

        closed = TradeOutcome(
            entry_timestamp=trade.entry_timestamp,
            exit_timestamp=timestamp,
            candidate=c,
            signal=trade.signal,
            source_strategy=trade.source_strategy,
            instrument=trade.instrument,
            pnl=pnl,
            result=result,
        )
        self._trades.append(closed)
        self._balance += pnl
        if self._balance > self._peak_balance:
            self._peak_balance = self._balance
        self._open_trade = None

    def resolve_at_cursor(self, candle: Candle, max_hold_days: int = 10) -> None:
        if self._open_trade is None:
            return
        c = self._open_trade.candidate
        days_held = (candle.timestamp - self._open_trade.entry_timestamp).days
        if days_held >= max_hold_days:
            self.close_trade(candle.close, candle.timestamp)
            return

        if candle.timestamp == self._open_trade.entry_timestamp:
            if self._resolve_fill_candle_gap(candle):
                return

        if c.direction == TrendDirection.BULLISH:
            if candle.low <= c.stop:
                self.close_trade(c.stop, candle.timestamp)
            elif candle.high >= c.target:
                self.close_trade(c.target, candle.timestamp)
        else:
            if candle.high >= c.stop:
                self.close_trade(c.stop, candle.timestamp)
            elif candle.low <= c.target:
                self.close_trade(c.target, candle.timestamp)

    def _resolve_fill_candle_gap(self, candle: Candle) -> bool:
        """Close at the open when the fill candle gapped through stop/target.

        A position filled at the candle's open cannot capture a move that
        happened before entry; if the open already breached a level, exit at
        that open rather than at a stop/target that sits on the wrong side of
        the fill price. Returns True when the trade was closed.
        """
        if self._open_trade is None:
            return False
        c = self._open_trade.candidate
        if c.direction == TrendDirection.BULLISH:
            if candle.open >= c.target or candle.open <= c.stop:
                self.close_trade(candle.open, candle.timestamp)
                return True
        else:
            if candle.open <= c.target or candle.open >= c.stop:
                self.close_trade(candle.open, candle.timestamp)
                return True
        return False

    def filtered_by_instrument(self, canonical: str) -> TradeBook:
        """A copy of the book holding only ``canonical``'s closed trades.

        The shared book is untouched; balance, peak, and drawdown are recomputed
        from the subset so per-instrument charts and summaries stay internally
        consistent (backlog 077).
        """
        book = TradeBook(self._initial_balance)
        subset = [t for t in self._trades if t.instrument == canonical]
        book._trades = subset
        book._balance = self._initial_balance + sum(
            float(t.pnl) for t in subset if t.pnl is not None
        )
        peak = self._initial_balance
        balance = self._initial_balance
        for trade in subset:
            if trade.pnl is not None:
                balance += trade.pnl
            if balance > peak:
                peak = balance
        book._peak_balance = peak
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
            "by_strategy": self._strategy_breakdown(),
            "by_instrument": self._instrument_breakdown(),
        }

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
