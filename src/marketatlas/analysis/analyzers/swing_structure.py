from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.structural import SwingFact, SwingType, SwingStructureFact


class SwingStructureAnalyzer(Analyzer):
    def __init__(
        self,
        window: int = 20,
        swing_key: str = "swing",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._window = window
        self._swing_key = swing_key

    @property
    def instance_key(self) -> str:
        return "swing_structure"

    def requires(self) -> tuple[FactKey, ...]:
        return (self._make_key(self._swing_key),)

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        swing_fact = facts.get(self._make_key(self._swing_key))

        if not isinstance(swing_fact, SwingFact) or not swing_fact.swings:
            evidence: tuple[EvidenceEntry, ...] = (
                EvidenceEntry(
                    text="No S/R levels — no swings available",
                    level=EvidenceLevel.INFO,
                    source="SupportResistanceAnalyzer",
                ),
            )
            return AnalysisResult(
                facts=(
                    SwingStructureFact(
                        timestamp=view.current.timestamp,
                        evidence=evidence,
                        points=(),
                    ),
                ),
                evidence=evidence,
            )

        swings = swing_fact.swings[-5:]

        pattern = "".join([{SwingType.LOW: "L", SwingType.HIGH: "H"}[s.type] for s in swings])
        if pattern == "LHLHL" or pattern == "HLHLH":
            # alternating pattern detected
            evidence_list: list[EvidenceEntry] = [
                EvidenceEntry(
                    text=("Detected alternating swing points"),
                    level=EvidenceLevel.INFO,
                    source="SwingStructureAnalyzer",
                ),
            ]

            return AnalysisResult(
                facts=(
                    SwingStructureFact(
                        timestamp=view.current.timestamp,
                        evidence=tuple(evidence_list),
                        points=swings,
                    ),
                ),
                evidence=tuple(evidence_list),
            )

        # return with no pattern found
        no_pattern_evidence: tuple[EvidenceEntry, ...] = (
            EvidenceEntry(
                text="most recent swings are not in an alternating pattern",
                level=EvidenceLevel.INFO,
                source="SwingStructureAnalyzer",
            ),
        )
        return AnalysisResult(
            facts=(),
            evidence=no_pattern_evidence,
        )
