"""Trade ledger: portfolio accounting (balance, peak, drawdown, equity curve).

Owns the compounding cash balance, running peak, and a time-indexed balance
series (the equity curve). Trade lifecycle and reporting live elsewhere — this
is the single owner of equity accounting so a change to position sizing or P&L
application touches only here.
"""

from __future__ import annotations

from datetime import datetime


class TradeLedger:
    """Compounding account balance and peak tracking.

    ``apply`` credits a closed trade's P&L into the cash balance, keeping the
    running peak current. ``max_drawdown`` is a pure read over a sequence of
    realized P&Ls relative to the initial balance. A timestamped ``apply`` also
    appends the post-close balance to the equity curve.
    """

    def __init__(self, initial_balance: float = 1000.0) -> None:
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._peak_balance = initial_balance
        self._curve: list[tuple[datetime, float]] = []

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def initial_balance(self) -> float:
        return self._initial_balance

    @property
    def peak_balance(self) -> float:
        return self._peak_balance

    @property
    def total_pnl(self) -> float:
        return self._balance - self._initial_balance

    @property
    def equity_curve(self) -> tuple[tuple[datetime, float], ...]:
        """Time-indexed balance series, one point per (timestamped) close.

        Each entry is ``(close_time, balance_after_that_close)`` in close
        order. Unsatisfied closes (never timestamped) contribute nothing; the
        series granularity is per-closed-trade, which is enough for
        annualization and drawdown analysis.
        """
        return tuple(self._curve)

    def apply(self, pnl: float, timestamp: datetime | None = None) -> None:
        """Credit a realized P&L and update the running peak (and curve)."""
        self._balance += pnl
        if self._balance > self._peak_balance:
            self._peak_balance = self._balance
        if timestamp is not None:
            self._curve.append((timestamp, self._balance))

    @staticmethod
    def max_drawdown(pnls: tuple[float, ...], initial_balance: float) -> float:
        """Worst peak-to-trough drawdown over a realized P&L sequence."""
        if not pnls:
            return 0.0
        peak = initial_balance
        worst = 0.0
        balance = initial_balance
        for pnl in pnls:
            balance += pnl
            if balance > peak:
                peak = balance
            drawdown = (peak - balance) / peak if peak > 0 else 0.0
            if drawdown > worst:
                worst = drawdown
        return worst
