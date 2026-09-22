"""Metrics layer: trade-level (099), portfolio-level (100), costs (101),
robustness + report (102) engines.

Pure functions over plain dicts; JSON-serializable at the boundary.
"""

from marketatlas.metrics import costs, drawdown, portfolio, report, robustness, stats
from marketatlas.metrics.costs import CostSchedule, apply_cost_schedule, net_metrics
from marketatlas.metrics.portfolio import portfolio_metrics
from marketatlas.metrics.report import build_report, format_report_text
from marketatlas.metrics.robustness import (
    monte_carlo,
    out_of_sample_split,
    risk_sensitivity,
    walk_forward,
)
from marketatlas.metrics.trades import trade_metrics

__all__ = [
    "CostSchedule",
    "apply_cost_schedule",
    "build_report",
    "costs",
    "drawdown",
    "format_report_text",
    "monte_carlo",
    "net_metrics",
    "out_of_sample_split",
    "portfolio",
    "portfolio_metrics",
    "report",
    "risk_sensitivity",
    "robustness",
    "stats",
    "trade_metrics",
    "walk_forward",
]
