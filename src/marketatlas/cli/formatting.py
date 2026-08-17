from __future__ import annotations


def _ab_row(label: str, summary: dict[str, object]) -> str:
    """One comparison line: trades, W/L, P&L, return, drawdown, PF, expectancy."""
    return (
        f"{label:<40s}"
        f"{summary['total_trades']:3d} trades "
        f"{summary['wins']}W/{summary['losses']}L "
        f"P&L=${summary['total_pnl']:+.2f} "
        f"({summary['total_return_pct']:+.1f}%) "
        f"DD={summary['max_drawdown']:.1%} "
        f"PF={summary['profit_factor']:.2f} "
        f"EXP=${summary['expectancy']:.2f}"
    )
