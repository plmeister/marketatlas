from dataclasses import dataclass
from enum import Enum


class EvidenceLevel(Enum):
    INFO = "info"
    SIGNAL = "signal"
    WARNING = "warning"


@dataclass(frozen=True)
class EvidenceEntry:
    text: str
    level: EvidenceLevel = EvidenceLevel.INFO
    source: str = ""
    annotation_hint: str = ""
