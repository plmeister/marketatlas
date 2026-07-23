from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import EMAFact


class EMAAnalyzer(Analyzer):
    def __init__(self, period: int = 20) -> None:
        self._period = period

    def requires(self) -> tuple[type[Fact], ...]:
        return ()

    def produces(self) -> tuple[type[Fact], ...]:
        return (EMAFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult:
        prices = view.prices
        period = min(self._period, len(prices))

        if period < 2:
            ema_value = prices[-1] if prices else 0.0
        else:
            k = 2.0 / (period + 1)
            sma = sum(prices[:period]) / period
            ema_value = sma
            for price in prices[period:]:
                ema_value = price * k + ema_value * (1 - k)

        evidence_entries: list[EvidenceEntry] = [
            EvidenceEntry(
                text=f"EMA{self._period} = {ema_value:.2f}",
                level=EvidenceLevel.INFO,
                source="EMAAnalyzer",
            ),
        ]

        if ema_value < view.current.close:
            evidence_entries.append(
                EvidenceEntry(
                    text=f"EMA{self._period} below price (bullish signal)",
                    level=EvidenceLevel.SIGNAL,
                    source="EMAAnalyzer",
                )
            )
        elif ema_value > view.current.close:
            evidence_entries.append(
                EvidenceEntry(
                    text=f"EMA{self._period} above price (bearish signal)",
                    level=EvidenceLevel.SIGNAL,
                    source="EMAAnalyzer",
                )
            )
        else:
            evidence_entries.append(
                EvidenceEntry(
                    text=f"EMA{self._period} at price (neutral)",
                    level=EvidenceLevel.INFO,
                    source="EMAAnalyzer",
                )
            )

        evidence = tuple(evidence_entries)

        return AnalysisResult(
            facts=(
                EMAFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    value=ema_value,
                    period=self._period,
                ),
            ),
            evidence=evidence,
        )
