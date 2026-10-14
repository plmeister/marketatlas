"""Magnitude-reversion signal — direction from a magnitude swing pivot.

The study's edge is mean reversion after a large move: a fractal pivot that
travelled at least ``k`` ATRs from the previous pivot marks the leg. The signal
emits on the bar where that pivot is *confirmed* (``confirm_lag`` bars after the
pivot bar, matching the detector's ``right_bars``) and fades it —

* pivot is a LOW  -> BULLISH (buy the drop),
* pivot is a HIGH -> BEARISH (sell the rally),

with an optional higher-timeframe range gate on the short side only: shorting a
swing high that has already broken *above* the trailing range (``w_pos >=
short_range_max``) is the losing case the detector study isolated, so shorts at
or above the range top are suppressed while longs are never gated.

Freshness is causal and exact: a pivot whose confirmation bar is not the current
bar produces no signal, so a stale swing cannot re-emit (the entry rule is
"enter on the confirmation close", not "enter any time the last swing is a low").
"""
from __future__ import annotations

from marketatlas.analysis.factkey import FactKey
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.structural import (
    RangePositionFact,
    SwingFact,
    SwingPoint,
    SwingType,
    TrendDirection,
)
from marketatlas.strategy.signals import (
    Signal,
    SignalEvaluation,
    TradeSignal,
    resolve_fact_key,
)


def _fmt_p(value: float) -> str:
    ax = abs(value)
    dp = 2 if ax >= 100 else 4 if ax >= 1 else 6
    return f"{value:.{dp}f}"


class MagnitudeReversionSignal(Signal):
    """Fade a freshly-confirmed magnitude swing, gated on range position for shorts."""

    def __init__(
        self,
        magnitude_swings: str = "magnitude_swings",
        range_position: str = "range_position",
        confirm_lag: int = 2,
        enable_short_filter: bool = True,
        short_range_max: float = 0.8,
    ) -> None:
        self._swing_key = magnitude_swings
        self._range_key = range_position
        self._confirm_lag = confirm_lag
        self._enable_short_filter = enable_short_filter
        self._short_range_max = short_range_max

    def requires(self) -> tuple[FactKey, ...]:
        return (FactKey(self._swing_key), FactKey(self._range_key))

    def evaluate(self, view: MarketView, facts: dict[FactKey, Fact]) -> TradeSignal | None:
        return self._evaluate(view, facts).signal

    def evaluate_with_rejections(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> SignalEvaluation:
        return self._evaluate(view, facts)

    def _evaluate(self, view: MarketView, facts: dict[FactKey, Fact]) -> SignalEvaluation:
        swing_key = resolve_fact_key(facts, self._swing_key)
        swing_fact = facts.get(swing_key) if swing_key is not None else None
        if not isinstance(swing_fact, SwingFact) or not swing_fact.swings:
            return SignalEvaluation()

        pivot = swing_fact.swings[-1]
        if not self._is_fresh(view, pivot):
            return SignalEvaluation()

        if pivot.type == SwingType.LOW:
            direction = TrendDirection.BULLISH
        elif pivot.type == SwingType.HIGH:
            direction = TrendDirection.BEARISH
        else:
            return SignalEvaluation()

        if direction == TrendDirection.BEARISH and self._enable_short_filter:
            rejected = self._short_gate(facts, pivot)
            if rejected is not None:
                return rejected

        close = view.current.close
        evidence: tuple[EvidenceEntry, ...] = (
            EvidenceEntry(
                text=(
                    f"Signal: {direction.value} — fade {pivot.type.value} pivot "
                    f"{_fmt_p(pivot.price)} confirmed {self._confirm_lag} bars ago"
                ),
                level=EvidenceLevel.SIGNAL,
                source="MagnitudeReversionSignal",
            ),
            EvidenceEntry(
                text=f"Entry zone: {_fmt_p(close)} (signal close)",
                level=EvidenceLevel.INFO,
                source="MagnitudeReversionSignal",
            ),
        )
        return SignalEvaluation(
            signal=TradeSignal(
                direction=direction,
                entry_zone=(close, close),
                confidence=1.0,
                source="MagnitudeReversionSignal",
                evidence=evidence,
            )
        )

    def _short_gate(
        self, facts: dict[FactKey, Fact], pivot: SwingPoint
    ) -> SignalEvaluation | None:
        """Return a rejection when a short is not allowed, else ``None``."""
        range_key = resolve_fact_key(facts, self._range_key)
        rng = facts.get(range_key) if range_key is not None else None
        if not isinstance(rng, RangePositionFact):
            return self._rejected("no range-position fact to gate the short")
        if rng.position is None:
            return self._rejected("range position undefined; short not confirmable")
        if rng.position >= self._short_range_max:
            return self._rejected(
                f"short at {pivot.type.value} in/above trailing range "
                f"(w_pos {rng.position:.2f} >= {self._short_range_max:.2f})"
            )
        return None

    def _is_fresh(self, view: MarketView, pivot: SwingPoint) -> bool:
        """True only on the pivot's confirmation bar (causal, exact)."""
        timestamps = view.timestamps
        try:
            idx = timestamps.index(pivot.timestamp)
        except ValueError:
            return False
        return (len(timestamps) - 1 - idx) == self._confirm_lag

    def _rejected(self, reason: str) -> SignalEvaluation:
        return SignalEvaluation(
            rejections=(
                EvidenceEntry(
                    text=f"Rejected: {reason}",
                    level=EvidenceLevel.WARNING,
                    source="MagnitudeReversionSignal",
                ),
            )
        )
