from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from marketatlas.analysis.factkey import FactKey
from marketatlas.data.types import Candle
from marketatlas.evidence.model import EvidenceEntry
from marketatlas.facts.base import Fact

if TYPE_CHECKING:
    from marketatlas.strategy.signals import TradeSignal


@dataclass(frozen=True)
class AnalysisFrame:
    timestamp: datetime
    candle: Candle
    facts: dict[FactKey, Fact]
    evidence: tuple[EvidenceEntry, ...]
    annotations: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    signals: tuple["TradeSignal", ...] = ()
    risk_evidence: tuple[EvidenceEntry, ...] = ()
    signal_rejections: tuple[EvidenceEntry, ...] = ()
