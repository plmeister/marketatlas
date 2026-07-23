from dataclasses import dataclass
from datetime import datetime

from marketatlas.data.types import Candle
from marketatlas.evidence.model import EvidenceEntry
from marketatlas.facts.base import Fact

FactKey = tuple[type[Fact], str]


@dataclass(frozen=True)
class AnalysisFrame:
    timestamp: datetime
    candle: Candle
    facts: dict[FactKey, Fact]
    evidence: tuple[EvidenceEntry, ...]
    annotations: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
