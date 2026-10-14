"""Fixed-ATR bracket risk node — the magnitude-reversion study geometry.

Independent of :class:`~marketatlas.strategy.risk.RiskEngine`. Where that node
anchors the stop to structure (swings / S/R) and selects the target from an RR
band, this node is the geometry the study validated: a symmetric ATR bracket
measured off the signal close.

    entry  = close (+/- entry_buffer_atr * ATR, then +/- slippage)
    stop   = entry -/+ stop_atr * ATR
    target = entry +/- target_atr * ATR      (RR = target_atr / stop_atr)

No S/R filtering, no scale-out, no RR search. The stop is always exactly
``stop_atr`` ATRs wide, so sizing at ``risk_pct`` is stable trade to study.

The study's bracket is ``1.5 / 3.0`` ATR off the signal close with a pivot-bar
SMA-ATR; wiring the same ATR *series* the detector used (and horizon 15) is what
makes a run comparable, not this node alone.
"""
from __future__ import annotations

import math
from datetime import datetime

from marketatlas.analysis.factkey import FactKey
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRSeriesFact
from marketatlas.facts.structural import SwingFact, TrendDirection
from marketatlas.strategy.signals import TradeSignal, resolve_fact_key
from marketatlas.strategy.trade import TradeCandidate


def _value_at(series: ATRSeriesFact, timestamp: datetime) -> float | None:
    """ATR series value at ``timestamp`` (latest at-or-before; points sorted)."""
    latest: float | None = None
    for point in series.points:
        if point.timestamp <= timestamp:
            latest = point.value
        else:
            break
    return latest


def _fmt_p(value: float) -> str:
    """Magnitude-aware price formatting (mirrors RiskEngine._fmt_p)."""
    if value is None or value != value or not math.isfinite(value):
        return ""
    ax = abs(value)
    dp = 2 if ax >= 100 else 4 if ax >= 1 else 6
    raw = f"{value:.{dp}f}"
    if "." not in raw:
        return raw
    trimmed = raw.rstrip("0")
    if trimmed.endswith("."):
        trimmed = trimmed[:-1]
    if "." not in trimmed:
        return f"{value:.{dp}f}"
    frac = trimmed.split(".", 1)[1]
    if len(frac) < 2:
        return f"{value:.{dp}f}"
    return trimmed


class AtrBracketRisk:
    """Fixed ATR stop/target bracket off the signal close.

    ``stop_atr`` and ``target_atr`` are ATR multiples; ``RR = target_atr /
    stop_atr``. ``entry_buffer_atr`` shifts the entry off the close (0 =
    enter at the signal close, the study's rule). ``max_hold_days`` is carried
    for parity with :class:`RiskEngine` — the backtester's own ``max_hold_days``
    drives the max-hold exit.
    """

    def __init__(
        self,
        stop_atr: float = 1.5,
        target_atr: float = 3.0,
        risk_pct: float = 1.0,
        entry_buffer_atr: float = 0.0,
        slippage_pct: float = 0.0,
        max_hold_days: int = 15,
        atr_key: str = "atr_14_series",
        swing_key: str = "magnitude_swings",
        bindings: dict[str, str] | None = None,
    ) -> None:
        if stop_atr <= 0:
            raise ValueError("stop_atr must be positive")
        if target_atr <= 0:
            raise ValueError("target_atr must be positive")
        self._stop_atr = stop_atr
        self._target_atr = target_atr
        self._risk_pct = risk_pct
        self._entry_buffer_atr = entry_buffer_atr
        self._slippage_pct = slippage_pct
        self._max_hold_days = max_hold_days
        self._atr_key = atr_key
        self._swing_key = swing_key
        self._bindings = dict(bindings) if bindings else {}

    @property
    def max_hold_days(self) -> int:
        return self._max_hold_days

    def requires(self) -> tuple[FactKey, ...]:
        return (FactKey(self._atr_key), FactKey(self._swing_key))

    def produces(self) -> tuple[FactKey, ...]:
        return ()

    def evaluate(
        self,
        signal: TradeSignal,
        facts: dict[FactKey, Fact],
        view: MarketView,
        balance: float = 1000.0,
    ) -> tuple[TradeCandidate | None, tuple[EvidenceEntry, ...]]:
        swing_key = resolve_fact_key(facts, self._swing_key)
        swing = facts.get(swing_key) if swing_key is not None else None
        if not isinstance(swing, SwingFact) or not swing.swings:
            return None, (
                EvidenceEntry(
                    text="Rejected: no swing fact for the ATR bracket",
                    level=EvidenceLevel.WARNING,
                    source="AtrBracketRisk",
                ),
            )

        series_key = resolve_fact_key(
            facts, self._bindings.get("atr_14_series", self._atr_key)
        )
        series = facts.get(series_key) if series_key is not None else None
        if not isinstance(series, ATRSeriesFact):
            return None, (
                EvidenceEntry(
                    text="Rejected: no ATR series fact for the ATR bracket",
                    level=EvidenceLevel.WARNING,
                    source="AtrBracketRisk",
                ),
            )

        pivot = swing.swings[-1]
        atr_val = _value_at(series, pivot.timestamp)
        if atr_val is None or atr_val <= 0:
            return None, (
                EvidenceEntry(
                    text="Rejected: no valid ATR at the signal pivot bar",
                    level=EvidenceLevel.WARNING,
                    source="AtrBracketRisk",
                ),
            )

        close_price = view.current.close
        risk_multiplier = getattr(signal, "risk_multiplier", 1.0)

        if signal.direction == TrendDirection.BULLISH:
            raw_entry = close_price + self._entry_buffer_atr * atr_val
            entry = raw_entry * (1 + self._slippage_pct / 100)
        else:
            raw_entry = close_price - self._entry_buffer_atr * atr_val
            entry = raw_entry * (1 - self._slippage_pct / 100)

        stop_distance = self._stop_atr * atr_val
        rr_ratio = self._target_atr / self._stop_atr
        if signal.direction == TrendDirection.BULLISH:
            stop = entry - stop_distance
            target = entry + self._target_atr * atr_val
        else:
            stop = entry + stop_distance
            target = entry - self._target_atr * atr_val

        risk_amount = balance * (self._risk_pct / 100) * risk_multiplier
        size = risk_amount / stop_distance
        reward_amount = rr_ratio * risk_amount

        evidence: tuple[EvidenceEntry, ...] = (
            EvidenceEntry(
                text=f"Stop: {_fmt_p(stop)} ({self._stop_atr:g} ATR bracket)",
                level=EvidenceLevel.INFO,
                source="AtrBracketRisk",
            ),
            EvidenceEntry(
                text=(
                    f"Target: {_fmt_p(target)} "
                    f"(RR {rr_ratio:.2f}, {self._target_atr:g} ATR bracket)"
                ),
                level=EvidenceLevel.INFO,
                source="AtrBracketRisk",
            ),
            EvidenceEntry(
                text=(
                    f"Size: {size:.4f} "
                    f"(risk {risk_amount:.2f} at {self._risk_pct:.1f}% of {balance:.2f})"
                ),
                level=EvidenceLevel.INFO,
                source="AtrBracketRisk",
            ),
        )
        return (
            TradeCandidate(
                direction=signal.direction,
                entry=entry,
                stop=stop,
                target=target,
                size=size,
                risk_amount=risk_amount,
                reward_amount=reward_amount,
                rr_ratio=rr_ratio,
                slippage_pct=self._slippage_pct,
                source=signal.source,
                evidence=evidence,
            ),
            evidence,
        )
