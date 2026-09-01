from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from marketatlas.data.types import Candle

if TYPE_CHECKING:
    from marketatlas.backtesting.backtester import BacktestResult
    from marketatlas.backtesting.portfolio import PortfolioBacktestResult
    from marketatlas.data.store import MarketStore
    from marketatlas.frames.frame import AnalysisFrame
    from marketatlas.strategy.tradebook import TradeOutcome


def _summary(tradebook: "Any") -> dict[str, Any]:
    s = tradebook.summary
    assert isinstance(s, dict)
    return s


@dataclass(frozen=True)
class AnalysisSummary:
    """Materialized, store-independent run statistics.

    Mirrors ``TradeBook.summary()`` but as a typed object so consumers (HTML,
    tables, comparisons) read data instead of poking at a live ``TradeBook``.
    """

    initial_balance: float
    final_balance: float
    total_pnl: float
    total_return_pct: float
    total_trades: int
    wins: int
    losses: int
    breakevens: int
    win_rate: float
    peak_balance: float
    max_drawdown: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    expectancy: float
    by_strategy: dict[str, dict[str, Any]]
    by_instrument: dict[str, dict[str, Any]]

    @classmethod
    def from_tradebook(cls, tradebook: "Any") -> "AnalysisSummary":
        s = _summary(tradebook)
        return cls(
            initial_balance=s["initial_balance"],
            final_balance=s["final_balance"],
            total_pnl=s["total_pnl"],
            total_return_pct=s["total_return_pct"],
            total_trades=s["total_trades"],
            wins=s["wins"],
            losses=s["losses"],
            breakevens=s.get("breakevens", 0),
            win_rate=s["win_rate"],
            peak_balance=s.get("peak_balance", s["final_balance"]),
            max_drawdown=s["max_drawdown"],
            gross_profit=s.get("gross_profit", 0.0),
            gross_loss=s.get("gross_loss", 0.0),
            profit_factor=s.get("profit_factor", 0.0),
            avg_win=s.get("avg_win", 0.0),
            avg_loss=s.get("avg_loss", 0.0),
            expectancy=s["expectancy"],
            by_strategy=s.get("by_strategy", {}),
            by_instrument=s.get("by_instrument", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict form for JSON serialization / stats tables."""
        return {
            "initial_balance": self.initial_balance,
            "final_balance": self.final_balance,
            "total_pnl": self.total_pnl,
            "total_return_pct": self.total_return_pct,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "breakevens": self.breakevens,
            "win_rate": self.win_rate,
            "peak_balance": self.peak_balance,
            "max_drawdown": self.max_drawdown,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "profit_factor": self.profit_factor,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "expectancy": self.expectancy,
            "by_strategy": self.by_strategy,
            "by_instrument": self.by_instrument,
        }


@dataclass(frozen=True)
class AnalysisOutput:
    """Canonical, store-independent result of an analysis run.

    Carries everything a human-facing overview needs — the price series per
    timeframe, the per-cursor frames, the traded outcomes and the typed summary.
    It never references a live ``MarketStore`` or ``TradeBook``; the HTML chart
    (or any table/comparison/report) is built purely from this object.
    """

    symbol: str
    timeframe: str
    timeframes: tuple[str, ...]
    candles: dict[str, tuple[Candle, ...]]
    frames: tuple["AnalysisFrame", ...]
    trades: tuple["TradeOutcome", ...]
    summary: AnalysisSummary
    window_size: int
    max_hold_days: int
    title: str = ""

    @classmethod
    def from_backtest_result(cls, result: "BacktestResult") -> "AnalysisOutput":
        store = result.store
        symbol = (
            f"{store.symbol.name}"
            if getattr(store, "symbol", None) is not None
            else getattr(result, "symbol", "")
        )
        timeframe = (
            store.timeframe.value
            if getattr(store, "timeframe", None) is not None
            else ""
        )
        tf_values = [tf.value for tf in store.available_timeframes]
        candles = {
            tf.value: tuple(store.get_candles(tf))
            for tf in store.available_timeframes
            if store.get_candles(tf)
        }
        title = symbol
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            timeframes=tuple(tf_values),
            candles=candles,
            frames=tuple(result.frames),
            trades=result.tradebook.trades,
            summary=AnalysisSummary.from_tradebook(result.tradebook),
            window_size=result.window_size,
            max_hold_days=result.max_hold_days,
            title=title,
        )

    @classmethod
    def _from_store_and_book(
        cls,
        store: "MarketStore",
        frames: tuple["AnalysisFrame", ...],
        trades: tuple["TradeOutcome", ...],
        tradebook: "Any",
        window_size: int,
        max_hold_days: int,
        title: str,
    ) -> "AnalysisOutput":
        tf_values = [tf.value for tf in store.available_timeframes]
        candles = {
            tf.value: tuple(store.get_candles(tf))
            for tf in store.available_timeframes
            if store.get_candles(tf)
        }
        return cls(
            symbol=store.symbol.name,
            timeframe=store.timeframe.value,
            timeframes=tuple(tf_values),
            candles=candles,
            frames=frames,
            trades=trades,
            summary=AnalysisSummary.from_tradebook(tradebook),
            window_size=window_size,
            max_hold_days=max_hold_days,
            title=title,
        )


def from_portfolio_instrument(
    result: "PortfolioBacktestResult",
    canonical: str,
    store: "MarketStore",
) -> AnalysisOutput:
    """Per-instrument output: filtered trades + frames, that instrument's series."""
    from marketatlas.backtesting.portfolio import PortfolioBacktestResult  # noqa

    book = result.tradebook.filtered_by_instrument(canonical)
    return AnalysisOutput._from_store_and_book(
        store=store,
        frames=tuple(result.frames[canonical]),
        trades=book.trades,
        tradebook=book,
        window_size=result.window_size,
        max_hold_days=result.max_hold_days,
        title=canonical,
    )
