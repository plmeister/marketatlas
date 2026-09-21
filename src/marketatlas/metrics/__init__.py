"""Metrics layer: trade-level (099), portfolio-level (100), costs (101) engines.

Pure functions over plain dicts; JSON-serializable at the boundary. Backlog
102 (robustness/report) builds on ``stats`` + ``portfolio`` + ``costs``.
"""

from marketatlas.metrics import costs, drawdown, portfolio, stats
from marketatlas.metrics.costs import CostSchedule, apply_cost_schedule, net_metrics
from marketatlas.metrics.portfolio import portfolio_metrics
from marketatlas.metrics.trades import trade_metrics

__all__ = [
    "CostSchedule",
    "apply_cost_schedule",
    "costs",
    "drawdown",
    "net_metrics",
    "portfolio",
    "portfolio_metrics",
    "stats",
    "trade_metrics",
]
