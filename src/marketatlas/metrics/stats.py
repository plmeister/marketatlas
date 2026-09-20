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
