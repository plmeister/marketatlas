from dataclasses import dataclass
from datetime import datetime

from marketatlas.evidence.model import EvidenceEntry


@dataclass(frozen=True)
class Fact:
    timestamp: datetime
    evidence: tuple[EvidenceEntry, ...]
