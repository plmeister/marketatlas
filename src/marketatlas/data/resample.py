from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from marketatlas.data.types import Candle, Timeframe

_TF_MINUTES: Final[dict[Timeframe, int]] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
    Timeframe.D1: 1440,
    Timeframe.W1: 10080,
}


def _period_start(ts: datetime, timeframe: Timeframe) -> datetime:
    if timeframe == Timeframe.M1:
        return ts.replace(second=0, microsecond=0)
    if timeframe == Timeframe.M5:
        minute = ts.minute // 5 * 5
        return ts.replace(minute=minute, second=0, microsecond=0)
    if timeframe == Timeframe.M15:
        minute = ts.minute // 15 * 15
        return ts.replace(minute=minute, second=0, microsecond=0)
    if timeframe == Timeframe.M30:
        minute = ts.minute // 30 * 30
        return ts.replace(minute=minute, second=0, microsecond=0)
    if timeframe == Timeframe.H1:
        return ts.replace(minute=0, second=0, microsecond=0)
    if timeframe == Timeframe.H4:
        hour = ts.hour // 4 * 4
        return ts.replace(hour=hour, minute=0, second=0, microsecond=0)
    if timeframe == Timeframe.D1:
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if timeframe == Timeframe.W1:
        start = ts - timedelta(days=ts.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    return ts


def tf_minutes(timeframe: Timeframe) -> int:
    return _TF_MINUTES[timeframe]


class CannotResampleError(Exception):
    def __init__(self, source: Timeframe, target: Timeframe) -> None:
        self.source = source
        self.target = target
        super().__init__(
            f"Cannot resample from {source.value} to {target.value}: "
            f"source must be same or higher resolution"
        )


def resample(
    candles: tuple[Candle, ...],
    source_tf: Timeframe,
    target_tf: Timeframe,
) -> tuple[Candle, ...]:
    if source_tf == target_tf:
        return candles
    if _TF_MINUTES[source_tf] >= _TF_MINUTES[target_tf]:
        raise CannotResampleError(source_tf, target_tf)

    buckets: dict[datetime, list[Candle]] = {}
    for c in candles:
        key = _period_start(c.timestamp, target_tf)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(c)

    result: list[Candle] = []
    for key in sorted(buckets):
        group = buckets[key]
        result.append(
            Candle(
                timestamp=key,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
            )
        )
    return tuple(result)
