from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from marketatlas.data.types import Candle
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
    def win_rate(self) -> float:
        total = self.win_count + self.loss_count
        if total == 0:
            return 0.0
        return self.win_count / total

    @property
    def total_pnl(self) -> float:
        return self._balance - self._initial_balance

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
    ) -> None:
        self._pending_order = candidate
        self._pending_signal = signal
        self._pending_source = source
        self._pending_timestamp = signal_timestamp

    def fill_order(self, open_price: float, timestamp: datetime) -> None:
        if self._pending_order is None:
            return
        candidate = self._pending_order
        signal = self._pending_signal
        source = self._pending_source
        if candidate is None or signal is None:
            return
        self._open_trade = TradeOutcome(
            entry_timestamp=timestamp,
            exit_timestamp=None,
            candidate=candidate,
            signal=signal,
            source_strategy=source,
            pnl=None,
            result=None,
        )
        self._pending_order = None
        self._pending_signal = None
        self._pending_source = ""
        self._pending_timestamp = None

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

    @property
    def summary(self) -> dict[str, object]:
        return {
            "initial_balance": self.initial_balance,
            "final_balance": self.balance,
            "total_pnl": self.total_pnl,
            "total_return_pct": (
                (self.total_pnl / self.initial_balance) * 100
                if self.initial_balance != 0
                else 0.0
            ),
            "total_trades": self.win_count + self.loss_count,
            "wins": self.win_count,
            "losses": self.loss_count,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "by_strategy": self._strategy_breakdown(),
        }

    def _strategy_breakdown(self) -> dict[str, dict[str, object]]:
        breakdown: dict[str, dict[str, object]] = {}
        for trade in self._trades:
            name = trade.source_strategy
            if name not in breakdown:
                breakdown[name] = {
                    "wins": 0,
                    "losses": 0,
                    "total_pnl": 0.0,
                }
            entry = breakdown[name]
            if trade.result == "win":
                entry["wins"] = entry["wins"] + 1  # type: ignore[operator]
            elif trade.result == "loss":
                entry["losses"] = entry["losses"] + 1  # type: ignore[operator]
            if trade.pnl is not None:
                entry["total_pnl"] = entry["total_pnl"] + trade.pnl  # type: ignore[operator]
        return breakdown
