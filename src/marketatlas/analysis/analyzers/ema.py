from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.math import compute_ema
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import EMAFact


class EMAAnalyzer(Analyzer):
    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def instance_key(self) -> str:
        return f"ema_{self._period}"

    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        ema_value = compute_ema(view.prices, self._period)

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
