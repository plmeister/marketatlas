from __future__ import annotations

from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.channel import ChannelFact


class ChannelAnalyzer(Analyzer):
    """Highest-high/lowest-low channel over a trailing window.

    The channel excludes the current candle (a breakout candle must never set
    its own boundary) and reports how many candles ago price last closed
    through either bound. Conservative, state-free, trivial to verify.
    """

    def __init__(self, period: int = 20, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._period = period

    @property
    def instance_key(self) -> str:
        return f"channel_{self._period}"

    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        highs = view.highs
        lows = view.lows
        closes = view.prices
        period = self._period

        high = max(highs[-period - 1 : -1]) if len(highs) > period else highs[-1] if highs else 0.0
        low = min(lows[-period - 1 : -1]) if len(lows) > period else lows[-1] if lows else 0.0
        breakout_days = self._breakout_age(closes, highs, lows, period)

        evidence = (
            EvidenceEntry(
                text=(
                    f"Channel{period} high {high:.2f} low {low:.2f} "
                    f"(last closed break {breakout_days}d ago)"
                ),
                level=EvidenceLevel.INFO,
                source="ChannelAnalyzer",
            ),
        )
        return AnalysisResult(
            facts=(
                ChannelFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    period=period,
                    high=high,
                    low=low,
                    breakout_days=breakout_days,
                ),
            ),
            evidence=evidence,
        )

    @staticmethod
    def _breakout_age(
        closes: tuple[float, ...],
        highs: tuple[float, ...],
        lows: tuple[float, ...],
        period: int,
    ) -> int:
        """Days since the last close that pierced the then-current channel.

        Each backstep compares its close against the trailing channel that
        existed at that time (excluding the candle itself), so a break only
        counts once it was truly above/below the prior range.
        """
        n = len(closes)
        if n < period + 2:
            return 0
        for age in range(n - 1, -1, -1):
            lo = age - period
            if lo < 0:
                break
            ch = max(highs[lo:age])
            cl = min(lows[lo:age])
            if closes[age] > ch or closes[age] < cl:
                return n - 1 - age
        return n - 1
