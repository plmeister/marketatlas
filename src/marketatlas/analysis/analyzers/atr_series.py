from typing import Any

from marketatlas.analysis.analyzers.atr_math import atr_series as _atr_series
from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRPoint, ATRSeriesFact


class ATRSeriesAnalyzer(Analyzer):
    """Per-candle ATR history (backlog 062).

    ``smoothing`` selects Wilder's recursive average (default) or a plain
    rolling SMA of true range (``"sma"``, matching the reference study's
    ``sma_atr``). ``lookback`` limits how many recent candles feed the
    computation; Wilder decays exponentially, so a bounded window is safe,
    while an SMA needs at least ``period`` trailing bars to be exact.
    """

    def __init__(
        self, period: int = 14, lookback: int = 0, smoothing: str = "wilder", **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self._period = period
        self._lookback = lookback
        self._smoothing = smoothing

    @property
    def instance_key(self) -> str:
        return self._name or f"atr_{self._period}_series"

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
        if len(candles) >= 2:
            highs = tuple(c.high for c in candles)
            lows = tuple(c.low for c in candles)
            closes = tuple(c.close for c in candles)
            values = _atr_series(highs, lows, closes, self._period, self._smoothing)
            for i in range(1, len(candles)):
                points.append(
                    ATRPoint(timestamp=candles[i].timestamp, value=values[i])
                )

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
