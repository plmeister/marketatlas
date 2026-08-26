from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact


class ATRAnalyzer(Analyzer):
    def __init__(self, period: int = 14, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._period = period
        self._store_state: dict[int, tuple[int, float, float]] = {}

    @property
    def instance_key(self) -> str:
        return f"atr_{self._period}"

    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def _compute_full(
        self, highs: tuple, lows: tuple, closes: tuple
    ) -> tuple[float, float]:
        """Returns (atr_value, running_sum_of_true_ranges)."""
        if len(highs) < 2:
            return (highs[0] - lows[0] if highs else 0.0, 0.0)
        true_ranges: list[float] = []
        for i in range(1, len(highs)):
            high_low = highs[i] - lows[i]
            high_prev_close = abs(highs[i] - closes[i - 1])
            low_prev_close = abs(lows[i] - closes[i - 1])
            true_ranges.append(max(high_low, high_prev_close, low_prev_close))
        period = min(self._period, len(true_ranges))
        if period == 0:
            return (0.0, 0.0)
        atr_value = sum(true_ranges[:period]) / period
        for tr in true_ranges[period:]:
            atr_value = (atr_value * (period - 1) + tr) / period
        return (atr_value, sum(true_ranges))

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        highs = view.highs
        lows = view.lows
        closes = view.prices
        cursor = len(highs)
        store_id = id(view.store)

        state = self._store_state.get(store_id)
        if state is not None:
            prev_cursor, prev_atr, prev_running_sum = state
        else:
            prev_cursor, prev_atr, prev_running_sum = -1, 0.0, 0.0

        if cursor == prev_cursor + 1 and cursor >= 2:
            i = cursor - 1
            high_low = highs[i] - lows[i]
            high_prev_close = abs(highs[i] - closes[i - 1])
            low_prev_close = abs(lows[i] - closes[i - 1])
            tr = max(high_low, high_prev_close, low_prev_close)
            running_sum = prev_running_sum + tr
            if i < self._period:
                atr_value = running_sum / i
            elif i == self._period:
                atr_value = running_sum / self._period
            else:
                atr_value = (prev_atr * (self._period - 1) + tr) / self._period
            self._store_state[store_id] = (cursor, atr_value, running_sum)
        else:
            atr_value, running_sum = self._compute_full(highs, lows, closes)
            self._store_state[store_id] = (cursor, atr_value, running_sum)

        pct_of_price = (atr_value / view.current.close * 100) if view.current.close else 0.0
        evidence: tuple[EvidenceEntry, ...] = (
            EvidenceEntry(
                text=f"ATR{self._period} = {atr_value:.2f}",
                level=EvidenceLevel.INFO,
                source="ATRAnalyzer",
            ),
            EvidenceEntry(
                text=f"ATR represents {pct_of_price:.2f}% of price",
                level=EvidenceLevel.INFO,
                source="ATRAnalyzer",
            ),
        )

        return AnalysisResult(
            facts=(
                ATRFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    value=atr_value,
                    period=self._period,
                ),
            ),
            evidence=evidence,
        )
