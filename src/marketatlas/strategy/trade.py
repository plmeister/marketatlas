from __future__ import annotations

from dataclasses import dataclass

from marketatlas.evidence.model import EvidenceEntry
from marketatlas.facts.structural import TrendDirection


@dataclass(frozen=True)
class TradeCandidate:
    direction: TrendDirection
    entry: float
    stop: float
    target: float
    size: float
    risk_amount: float
    reward_amount: float
    rr_ratio: float
    slippage_pct: float
    source: str
    evidence: tuple[EvidenceEntry, ...]
