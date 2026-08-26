from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRPoint, ATRSeriesFact


class ATRSeriesAnalyzer(Analyzer):
    """Per-candle ATR history using Wilder smoothing (backlog 062).

    ``lookback`` limits how many recent candles feed the computation.
    Wilder smoothing decays exponentially — after ~3×period candles old
    data contributes <3 % to the current value, so a bounded window
    gives accurate results at O(lookback) cost per call.
    """

    def __init__(self, period: int = 14, lookback: int = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._period = period
        self._lookback = lookback

    @property
    def instance_key(self) -> str:
        return f"atr_{self._period}_series"

    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        all_candles = view.series_through_cursor() + (view.current,)
        if self._lookback > 0:
            candles = all_candles[-self._lookback - 1 :]
        else:
            candles = all_candles

        points: list[ATRPoint] = []
        smoothed = 0.0
        running_sum = 0.0
        if len(candles) >= 2:
            for i in range(1, len(candles)):
                high_low = candles[i].high - candles[i].low
                high_prev_close = abs(candles[i].high - candles[i - 1].close)
                low_prev_close = abs(candles[i].low - candles[i - 1].close)
                tr = max(high_low, high_prev_close, low_prev_close)
                running_sum += tr
                if i < self._period:
                    value = running_sum / i
                elif i == self._period:
                    value = running_sum / self._period
                    smoothed = value
                else:
                    smoothed = (smoothed * (self._period - 1) + tr) / self._period
                    value = smoothed
                points.append(ATRPoint(timestamp=candles[i].timestamp, value=value))

        if points:
            last = points[-1].value
        else:
            last = candles[0].high - candles[0].low if candles else 0.0

        pct_of_price = (last / view.current.close * 100) if view.current.close else 0.0
        evidence: tuple[EvidenceEntry, ...] = (
            EvidenceEntry(
                text=f"ATR{self._period} series: {len(points)} per-candle values",
                level=EvidenceLevel.INFO,
                source="ATRSeriesAnalyzer",
            ),
            EvidenceEntry(
                text=f"ATR{self._period} = {last:.2f} ({pct_of_price:.2f}% of price)",
                level=EvidenceLevel.INFO,
                source="ATRSeriesAnalyzer",
            ),
        )

        return AnalysisResult(
            facts=(
                ATRSeriesFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    points=tuple(points),
                    period=self._period,
                ),
            ),
            evidence=evidence,
        )
