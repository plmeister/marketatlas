from __future__ import annotations

from dataclasses import dataclass

from marketatlas.facts.base import Fact


@dataclass(frozen=True)
class ChannelFact(Fact):
    """Trailing N-candle channel bounds plus range-break age.

    ``high``/``low`` are the channel extremes over the trailing ``period``
    candles (excluding the current candle, so the breakout candle never sets
    its own boundary). ``breakout_days`` counts candles since the last close
    pierced either bound — the channel's freshness, used to separate an
    outright range break from continuation structure.
    """

    period: int
    high: float
    low: float
    breakout_days: int
