"""Metrics layer: trade-level (099), portfolio-level (100) and drawdown engines.

Pure functions over plain dicts; JSON-serializable at the boundary. Backlogs
101 (costs) and 102 (robustness/report) build on ``stats`` + ``portfolio``.
"""

from marketatlas.metrics import drawdown, stats
from marketatlas.metrics.portfolio import portfolio_metrics
from marketatlas.metrics.trades import trade_metrics

__all__ = ["stats", "drawdown", "trade_metrics", "portfolio_metrics"]
