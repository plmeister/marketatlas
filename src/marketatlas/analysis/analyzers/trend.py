from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import TrendDirection, TrendFact


class TrendAnalyzer(Analyzer):
    def __init__(
        self,
        fast_key: str = "ema_20",
        slow_key: str = "ema_50",
        atr_key: str = "atr_14",
    ) -> None:
        self._fast_key = fast_key
        self._slow_key = slow_key
        self._atr_key = atr_key

    @property
    def instance_key(self) -> str:
        return "trend"

    def requires(self) -> tuple[FactKey, ...]:
        return (
            FactKey(self._fast_key),
            FactKey(self._slow_key),
        )

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey(self.instance_key),)

    def analyze(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> AnalysisResult:
        fast_ema_fact = facts[FactKey(self._fast_key)]
        slow_ema_fact = facts[FactKey(self._slow_key)]
        assert isinstance(fast_ema_fact, EMAFact)
        assert isinstance(slow_ema_fact, EMAFact)
        fast_ema = fast_ema_fact.value
        slow_ema = slow_ema_fact.value

        if fast_ema > slow_ema:
            direction = TrendDirection.BULLISH
        elif fast_ema < slow_ema:
            direction = TrendDirection.BEARISH
        else:
            direction = TrendDirection.NEUTRAL

        atr_value = 0.0
        atr_fact = facts.get(FactKey(self._atr_key))
        if atr_fact is not None and isinstance(atr_fact, ATRFact):
            atr_value = atr_fact.value

        spread = abs(fast_ema - slow_ema)
        if atr_value > 0:
            strength = min(1.0, spread / atr_value)
        else:
            price = view.current.close
            strength = min(1.0, spread / price) if price > 0 else 0.0

        price = view.current.close
        above_both = price > fast_ema and price > slow_ema
        below_both = price < fast_ema and price < slow_ema

        cmp = ">" if fast_ema > slow_ema else "<"
        evidence_entries: list[EvidenceEntry] = [
            EvidenceEntry(
                text=(
                    f"Trend: {direction.value.title()} — "
                    f"Fast EMA ({fast_ema:.2f}) {cmp} "
                    f"Slow EMA ({slow_ema:.2f})"
                ),
                level=EvidenceLevel.INFO,
                source="TrendAnalyzer",
            ),
            EvidenceEntry(
                text=f"Strength: {strength:.2f} — spread {spread:.2f}",
                level=EvidenceLevel.INFO,
                source="TrendAnalyzer",
            ),
        ]
        if above_both:
            evidence_entries.append(
                EvidenceEntry(
                    text="Confirmed by price above both EMAs",
                    level=EvidenceLevel.SIGNAL,
                    source="TrendAnalyzer",
                )
            )
        elif below_both:
            evidence_entries.append(
                EvidenceEntry(
                    text="Confirmed by price below both EMAs",
                    level=EvidenceLevel.SIGNAL,
                    source="TrendAnalyzer",
                )
            )

        evidence = tuple(evidence_entries)

        return AnalysisResult(
            facts=(
                TrendFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    direction=direction,
                    strength=round(strength, 4),
                ),
            ),
            evidence=evidence,
        )
