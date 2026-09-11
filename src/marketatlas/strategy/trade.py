from __future__ import annotations

from dataclasses import dataclass

from marketatlas.evidence.model import EvidenceEntry
from marketatlas.facts.structural import TrendDirection


@dataclass(frozen=True)
class ExitPlan:
    """De-risk exit geometry for a trade.

    Two modes, mutually exclusive in practice:

    * Scale-out (``scale_out_fraction > 0``): the position splits at
      ``scale_out_rr`` — that fraction is closed (banking its P&L) and the
      remainder runs on with a breakeven stop, optional trailing stop, and
      optional hard runner target.
    * Breakeven ratchet (``scale_out_fraction == 0`` and
      ``breakeven_at_rr > 0``): once price reaches ``breakeven_at_rr`` of
      the original stop distance, the single protective stop ratchets to
      entry (sellable as a plain stop-modification order). The submitted
      target is untouched. No partial fills.

    ``0.0`` everywhere disables de-risk exits entirely — the book resolves
    at the fixed stop/target exactly as before.
    """

    scale_out_fraction: float = 0.0
    scale_out_rr: float = 1.0
    breakeven_after_scale: bool = True
    runner_target_rr: float = 0.0
    trailing_stop_rr: float = 0.0
    breakeven_at_rr: float = 0.0

    @property
    def enabled(self) -> bool:
        return self.scale_out_fraction > 0 or self.breakeven_at_rr > 0


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
    min_rr: float = 0.0
    exit_plan: ExitPlan | None = None
