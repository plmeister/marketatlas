from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from marketatlas.evidence.model import EvidenceEntry
from marketatlas.facts.structural import TrendDirection


class ExitReason(str, Enum):
    """How a closed trade left the book (backlog 098).

    Values are the stable string forms stored in serialized output:

    * ``stop``    — protective stop (original, breakeven-ratcheted, or trailing) hit.
    * ``target``  — take-profit target hit.
    * ``timeout`` — time-driven close: max-hold expiry, or forced flatten at
      end-of-data while still open.
    * ``cancel``  — never filled / broker cancelled (open position recorded at
      0 P&L, or pending order dropped).

    ``reversal`` is reserved for a future signal-reversal exit.
    """

    STOP = "stop"
    TARGET = "target"
    TIMEOUT = "timeout"
    CANCEL = "cancel"
    REVERSAL = "reversal"


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
    # Entry execution model (backlog: EOD → next-open fills). ``entry_at_open``
    # fills the order at the next candle's open (broker processes post-close
    # orders at market open) instead of waiting for a touch of ``entry``;
    # ``reference_price`` is the signal close the gap guard measures against;
    # ``max_open_gap`` is the largest |open - reference| band tolerated (0 = off).
    entry_at_open: bool = False
    reference_price: float | None = None
    max_open_gap: float = 0.0
