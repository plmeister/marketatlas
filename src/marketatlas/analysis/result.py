from dataclasses import dataclass

from marketatlas.evidence.model import EvidenceEntry
from marketatlas.facts.base import Fact


@dataclass(frozen=True)
class AnalysisResult:
    facts: tuple[Fact, ...]
    evidence: tuple[EvidenceEntry, ...]
    diagnostics: tuple[str, ...] = ()
