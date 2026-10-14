"""Pure ATR computations shared by the scalar and series ATR analyzers.

Two smoothing conventions:

* ``wilder`` — Wilder's recursive average, seeded by the SMAs of the first
  ``period`` true ranges (the historical default).
* ``sma`` — a plain rolling simple moving average of true range, seeded by an
  expanding average. This matches the reference study's ``sma_atr`` and exists
  so the DSL can reproduce that study exactly.

Both return a per-candle list the same length as the input, with index ``0``
always ``0.0`` (no true range exists before the second bar).
"""

from __future__ import annotations

from collections.abc import Sequence

Smoothing = str


def true_ranges(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]
) -> list[float]:
    trs = [0.0] * len(closes)
    for i in range(1, len(closes)):
        trs[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    return trs


def sma_atr_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
) -> list[float]:
    trs = true_ranges(highs, lows, closes)
    atr = [0.0] * len(closes)
    run = 0.0
    for i in range(1, len(closes)):
        run += trs[i]
        if i > period:
            run -= trs[i - period]
        atr[i] = run / min(i, period)
    return atr


def wilder_atr_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
) -> list[float]:
    trs = true_ranges(highs, lows, closes)
    atr = [0.0] * len(closes)
    smoothed = 0.0
    running_sum = 0.0
    for i in range(1, len(closes)):
        running_sum += trs[i]
        if i < period:
            value = running_sum / i
        elif i == period:
            value = running_sum / period
            smoothed = value
        else:
            smoothed = (smoothed * (period - 1) + trs[i]) / period
            value = smoothed
        atr[i] = value
    return atr


def atr_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
    smoothing: Smoothing = "wilder",
) -> list[float]:
    if smoothing == "wilder":
        return wilder_atr_series(highs, lows, closes, period)
    if smoothing == "sma":
        return sma_atr_series(highs, lows, closes, period)
    raise ValueError(f"unknown ATR smoothing: {smoothing!r} (use 'wilder' or 'sma')")
