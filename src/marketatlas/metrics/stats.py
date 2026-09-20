"""Pure numeric helpers for the metrics layer.

No I/O, no third-party deps: percentiles, histograms, and distribution shape
statistics used by the trade-level (099) and portfolio-level (100) dashboards.
All functions are deterministic and JSON-serializable at the dict boundary.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

_NUM = int | float


def mean(values: Sequence[_NUM]) -> float | None:
    if not values:
        return None
    return float(statistics.fmean(values))


def median(values: Sequence[_NUM]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def percentile(values: Sequence[_NUM], p: float) -> float | None:
    """Linear-interpolated percentile (numpy ``linear`` method).

    ``p`` in [0, 1]. ``p=0.5`` is the median. Empty input yields ``None``.
    """
    if not values:
        return None
    srt = sorted(float(v) for v in values)
    if len(srt) == 1:
        return srt[0]
    pos = (len(srt) - 1) * p
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return srt[lo]
    frac = pos - lo
    return srt[lo] + frac * (srt[hi] - srt[lo])


def percentiles(values: Sequence[_NUM], ps: dict[str, float]) -> dict[str, float | None]:
    """Named percentiles, e.g. ``{"p25": 0.25, "p50": 0.5}``."""
    return {name: percentile(values, p) for name, p in ps.items()}


def histogram(values: Sequence[_NUM], n_bins: int = 10) -> dict[str, list[float] | list[int]]:
    """Equal-width histogram over finite values.

    Returns ``{"edges": [...], "counts": [...]}`` with ``len(edges) ==
    n_bins + 1`` in the general case and the upper edge snapped to the data
    maximum so the max value lands in the last bin. Degenerate inputs
    (empty, single value) collapse to a single bin.
    """
    nums = [float(v) for v in values if math.isfinite(float(v))]
    if not nums:
        return {"edges": [], "counts": []}
    lo, hi = min(nums), max(nums)
    if lo == hi:
        return {"edges": [lo, lo], "counts": [len(nums)]}
    if n_bins < 1:
        n_bins = 1
    width = (hi - lo) / n_bins
    edges = [lo + width * i for i in range(n_bins + 1)]
    edges[-1] = hi
    counts = [0] * n_bins
    for v in nums:
        idx = int((v - lo) / width)
        if idx >= n_bins:
            idx = n_bins - 1
        if idx < 0:
            idx = 0
        counts[idx] += 1
    return {"edges": edges, "counts": counts}


def _centered_moments(values: Sequence[_NUM]) -> tuple[float | None, float | None]:
    """Population mean and standard deviation; ``(None, None)`` if degenerate."""
    nums = [float(v) for v in values if math.isfinite(float(v))]
    if not nums:
        return None, None
    m = statistics.fmean(nums)
    var = statistics.pvariance(nums, mu=m)
    if var <= 0:
        return m, 0.0
    return m, math.sqrt(var)


def skewness(values: Sequence[_NUM]) -> float | None:
    """Population skewness (``mean(z**3)``); ``None`` when undefined."""
    nums = [float(v) for v in values if math.isfinite(float(v))]
    if len(nums) < 3:
        return None
    m, s = _centered_moments(nums)
    if m is None or s is None or s == 0.0:
        return None
    return sum(((v - m) / s) ** 3 for v in nums) / len(nums)


def kurtosis(values: Sequence[_NUM]) -> float | None:
    """Population excess kurtosis (``mean(z**4) - 3``); ``None`` when undefined."""
    nums = [float(v) for v in values if math.isfinite(float(v))]
    if len(nums) < 3:
        return None
    m, s = _centered_moments(nums)
    if m is None or s is None or s == 0.0:
        return None
    return sum(((v - m) / s) ** 4 for v in nums) / len(nums) - 3.0


# --- Time-series / portfolio helpers (backlog 100, reused by 102) -----------
# These operate on *period returns* (log or arithmetic) so the drawdown, Monte
# Carlo (102) and report layers share one annualization basis. ``periods_per_year``
# is always explicit: the caller decides whether a period is a bar (timeframe
# × bars-per-year) or a closed trade (observed closes per year).


def log_returns(values: Sequence[_NUM]) -> list[float]:
    """Log returns ``ln(v[i]/v[i-1])`` between consecutive ``>0`` values.

    Non-positive values are skipped entirely (their period is dropped); a
    zero/negative series yields ``[]``.
    """
    nums = [float(v) for v in values if math.isfinite(float(v))]
    out: list[float] = []
    for i in range(1, len(nums)):
        prev, cur = nums[i - 1], nums[i]
        if prev > 0.0 and cur > 0.0:
            out.append(math.log(cur / prev))
    return out


def product_returns(returns: Sequence[_NUM]) -> float | None:
    """Compounded (geometric) accumulated return: ``prod(1+r) - 1``.

    ``None`` for an empty series; used for compounded-vs-simple comparison.
    """
    if not returns:
        return None
    acc = 1.0
    for r in returns:
        acc *= 1.0 + float(r)
    return acc - 1.0


def annualized_geometric_return(
    log_returns_: Sequence[_NUM], periods_per_year: float
) -> float | None:
    """Compounded annual growth from a log-return series (geometric mean × ppr).

    ``exp(mean(ln g) * ppr) - 1``. ``None`` when no periods or ``ppr <= 0``.
    """
    if not log_returns_ or periods_per_year <= 0:
        return None
    total = sum(float(r) for r in log_returns_)
    return math.exp((total / len(log_returns_)) * periods_per_year) - 1.0


def cagr(final: _NUM, initial: _NUM, years: _NUM) -> float | None:
    """Compound annual growth rate ``(final/initial)^(1/years) - 1``.

    ``None`` when ``initial <= 0`` or ``years <= 0``.
    """
    if final <= 0 or initial <= 0 or years <= 0:
        return None
    base = float(final) / float(initial)
    exponent = 1.0 / float(years)
    return float(base**exponent) - 1.0


def volatility(log_returns_: Sequence[_NUM], periods_per_year: float) -> float | None:
    """Annualized volatility (sample std of log returns × sqrt(ppr)).

    Requires ≥2 periods; ``None`` otherwise. Uses sample standard deviation
    (ddof=1) so it matches ``numpy.std(..., ddof=1)``.
    """
    nums = [float(r) for r in log_returns_ if math.isfinite(float(r))]
    if len(nums) < 2 or periods_per_year <= 0:
        return None
    m = statistics.fmean(nums)
    var = statistics.variance(nums, m)
    if var < 0:
        return None
    return math.sqrt(var) * math.sqrt(periods_per_year)


def sharpe(
    log_returns_: Sequence[_NUM], periods_per_year: float, risk_free: float = 0.0
) -> float | None:
    """Annualized Sharpe ratio over excess log returns.

    ``(mean(excess) / sample_std(excess)) * sqrt(ppr)`` where per-period
    risk-free = ``risk_free / ppr`` (risk_free is an annual rate). ``None``
    when fewer than 2 periods survive or the excess series is flat.
    """
    if periods_per_year <= 0:
        return None
    per_period_rf = float(risk_free) / periods_per_year
    excess = [float(r) - per_period_rf for r in log_returns_ if math.isfinite(float(r))]
    if len(excess) < 2:
        return None
    m = statistics.fmean(excess)
    var = statistics.variance(excess, m)
    if var <= 0:
        return None
    return (m / math.sqrt(var)) * math.sqrt(periods_per_year)


def sortino(
    log_returns_: Sequence[_NUM], periods_per_year: float, target: float = 0.0
) -> float | None:
    """Annualized Sortino ratio (downside deviation below a target).

    MAR per period = ``target / ppr``; only periods returning below it count.
    Downside deviation = ``sqrt(mean(max(MAR - r, 0)**2)) * sqrt(ppr)``.
    Returns ``None`` when there is no downside at all (denominator 0) — the
    ratio is unbounded, mirroring how profit factor reports ``None`` for a
    zero-loss book.
    """
    if periods_per_year <= 0:
        return None
    nums = [float(r) for r in log_returns_ if math.isfinite(float(r))]
    if len(nums) < 2:
        return None
    mar = float(target) / periods_per_year
    shortfall = [max(mar - r, 0.0) ** 2 for r in nums if r < mar]
    if not shortfall:
        return None
    downside = math.sqrt(statistics.fmean(shortfall)) * math.sqrt(periods_per_year)
    if downside <= 0:
        return None
    mean = statistics.fmean(nums)
    annualized = mean * periods_per_year
    return (annualized - float(target)) / downside
