from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Fact:
    timestamp: datetime
    evidence: tuple[str, ...]
