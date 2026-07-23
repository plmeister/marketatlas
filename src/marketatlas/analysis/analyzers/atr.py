from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact


class ATRAnalyzer(Analyzer):
    def __init__(self, period: int = 14) -> None:
        self._period = period

    @property
    def instance_key(self) -> str:
        return f"atr_{self._period}"

    def requires(self) -> tuple[tuple[type[Fact], str], ...]:
        return ()

    def produces(self) -> tuple[tuple[type[Fact], str], ...]:
        return ((ATRFact, self.instance_key),)

    def analyze(
        self, view: MarketView, facts: dict[tuple[type[Fact], str], Fact]
    ) -> AnalysisResult:
        highs = view.highs
        lows = view.lows
        closes = view.prices

        if len(highs) < 2:
            atr_value = highs[0] - lows[0] if highs else 0.0
        else:
            true_ranges: list[float] = []
            for i in range(1, len(highs)):
                high_low = highs[i] - lows[i]
                high_prev_close = abs(highs[i] - closes[i - 1])
                low_prev_close = abs(lows[i] - closes[i - 1])
                true_ranges.append(max(high_low, high_prev_close, low_prev_close))

            period = min(self._period, len(true_ranges))
            if period == 0:
                atr_value = 0.0
            else:
                atr_value = sum(true_ranges[:period]) / period
                for tr in true_ranges[period:]:
                    atr_value = (atr_value * (period - 1) + tr) / period

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
