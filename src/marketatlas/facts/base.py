from dataclasses import dataclass, field
from datetime import datetime

from marketatlas.data.types import Timeframe
from marketatlas.evidence.model import EvidenceEntry


@dataclass(frozen=True, kw_only=True)
class Fact:
    timestamp: datetime
    evidence: tuple[EvidenceEntry, ...]
    visible_on: frozenset[Timeframe] | None = field(default=None, compare=False)
