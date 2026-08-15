import math
from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.types import Candle
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.pattern import PullbackFact
from marketatlas.facts.structural import (
    SwingPoint,
    SwingStructureFact,
    SwingType,
    TrendDirection,
)


class PullbackPatternAnalyzer(Analyzer):
    def __init__(
        self,
        swingstructure_key: str = "swing_structure",
        min_body_pct: float = 0.6,
        confirm_beyond_swing: bool = True,
        lookback_swings: int = 5,
        compact_candles: int = 40,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._swingstructure_key = swingstructure_key
        self._min_body_pct = min_body_pct
        self._confirm_beyond_swing = confirm_beyond_swing
        self._lookback_swings = lookback_swings
        self._compact_candles = compact_candles

    @property
    def instance_key(self) -> str:
        return "pullback_pattern"

    def requires(self) -> tuple[FactKey, ...]:
        return (self._make_key(self._swingstructure_key),)

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:

        struct = facts.get(self._make_key(self._swingstructure_key), None)

        if struct is None:
            evidence = (
                EvidenceEntry(
                    text="No pullback — not enough structured swings found",
                    level=EvidenceLevel.INFO,
                    source="PullbackDetector",
                ),
            )
            return AnalysisResult(
                facts=(),
                evidence=evidence,
            )

        assert isinstance(struct, SwingStructureFact)
        points = struct.points[-self._lookback_swings:]
        if not points:
            evidence = (
                EvidenceEntry(
                    text="No pullback — empty swing structure",
                    level=EvidenceLevel.INFO,
                    source="PullbackDetector",
                ),
            )
            return AnalysisResult(
                facts=(),
                evidence=evidence,
            )

        lows = [s for s in points if s.type == SwingType.LOW]
        highs = [s for s in points if s.type == SwingType.HIGH]

        all_higher_lows = all(b.price > a.price for a, b in zip(lows, lows[1:]))
        all_lower_lows = all(b.price < a.price for a, b in zip(lows, lows[1:]))

        all_higher_highs = all(b.price > a.price for a, b in zip(highs, highs[1:]))
        all_lower_highs = all(b.price < a.price for a, b in zip(highs, highs[1:]))

        direction = TrendDirection.NEUTRAL
        if len(lows) < 2 or len(highs) < 2:
            # not enough swing points to establish a pullback pattern
            evidence = (
                EvidenceEntry(
                    text="No pullback — not enough structured swings found",
                    level=EvidenceLevel.INFO,
                    source="PullbackDetector",
                ),
            )
            return AnalysisResult(
                facts=(),
                evidence=evidence,
            )
        if all_higher_lows and all_higher_highs:
            # this is a bullish pullback pattern
            direction = TrendDirection.BULLISH
        elif all_lower_lows and all_lower_highs:
            # this is a bearish pullback pattern
            direction = TrendDirection.BEARISH
        else:
            # no clear pullback pattern detected
            evidence = (
                EvidenceEntry(
                    text="No pullback — trend is neutral or ATR is zero",
                    level=EvidenceLevel.INFO,
                    source="PullbackDetector",
                ),
            )
            return AnalysisResult(
                facts=(),
                evidence=evidence,
            )

        last_swing = points[-1]

        # Entry-day gating (backlog 067): the pullback is only actionable on
        # the candle that follows the final swing point. The follow-up candle
        # is located by timestamp in the consumer's own timeframe, so the gate
        # works across timeframes (1w structure → 1d confirmation) where raw
        # indices are per-timeframe and not comparable.
        entry_idx = self._entry_day_index(view, last_swing)
        if entry_idx is None:
            evidence = (
                EvidenceEntry(
                    text=(
                        "Pullback structure complete; awaiting entry candle "
                        f"after swing at {last_swing.price:.2f}"
                    ),
                    level=EvidenceLevel.INFO,
                    source="PullbackDetector",
                ),
            )
            return AnalysisResult(
                facts=(),
                evidence=evidence,
            )
        if entry_idx < view.index:
            evidence = (
                EvidenceEntry(
                    text=(
                        "Pullback entry window missed — swing at "
                        f"{last_swing.price:.2f} not confirmed on entry candle"
                    ),
                    level=EvidenceLevel.INFO,
                    source="PullbackDetector",
                ),
            )
            return AnalysisResult(
                facts=(),
                evidence=evidence,
            )

        # Confirmation candle gate (single-candle, no read-ahead).
        reasons = self._confirmation_failures(view.current, direction, last_swing)
        if reasons:
            evidence = (
                EvidenceEntry(
                    text=(
                        "Pullback pattern detected but confirmation candle weak: "
                        f"{', '.join(reasons)} — no pullback placed"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="PullbackDetector",
                ),
            )
            return AnalysisResult(
                facts=(),
                evidence=evidence,
            )

        pattern: tuple[float, ...] = ()
        if len(lows) >= 2 and len(highs) >= 2:
            pts = sorted(
                (lows[-2], lows[-1], highs[-2], highs[-1]),
                key=lambda s: s.index,
            )
            pattern = tuple(p.price for p in pts)

        strength = self._pattern_strength(
            points,
            entry_close=view.current.close,
            direction=direction,
            compact_candles=self._compact_candles,
        )

        evidence = (
            EvidenceEntry(
                text=f"pullback detected {direction} on entry candle",
                level=EvidenceLevel.INFO,
                source="PullbackDetector",
            ),
        )
        return AnalysisResult(
            facts=(
                PullbackFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    direction=direction,
                    swing_pattern=pattern,
                    strength=strength,
                ),
            ),
            evidence=evidence,
        )

    @staticmethod
    def _pattern_strength(
        points: tuple[SwingPoint, ...],
        entry_close: float,
        direction: TrendDirection,
        compact_candles: int = 40,
    ) -> float:
        """Quality of the detected HH/HL structure as a pullback setup.

        Geometric mean of four terms, each in (0, 1]:
        * ``compactness`` — swings complete within ``compact_candles``.
        * ``leg_strength`` — legs move evenly (each leg vs. the longest leg).
        * ``pivot_quality`` — entry candle recovers a large share of the
          last swing's retracement (well-defined V).
        * ``inclination`` — trend legs outpace retracement legs (not flat).
        """
        if len(points) < 2:
            return 0.0
        legs = [abs(b.price - a.price) for a, b in zip(points, points[1:])]
        total = sum(legs)
        if total <= 0:
            return 0.0

        max_leg = max(legs)
        leg_strength = math.prod(min(leg / max_leg, 1.0) for leg in legs) ** (
            1.0 / len(legs)
        )

        span = points[-1].index - points[0].index
        compactness = max(0.0, 1.0 - span / max(compact_candles, 1))

        bullish = direction == TrendDirection.BULLISH
        last = points[-1]
        prev = points[-2]
        if bullish:
            drop = prev.price - last.price
            recovery = entry_close - last.price
        else:
            drop = last.price - prev.price
            recovery = last.price - entry_close
        pivot_quality = (
            min(drop, recovery) / max(drop, recovery)
            if drop > 0 and recovery > 0
            else 0.0
        )

        up_legs = sum(
            abs(b.price - a.price)
            for a, b in zip(points, points[1:])
            if (b.price - a.price) * (1 if bullish else -1) > 0
        )
        inclination = up_legs / total if total > 0 else 0.0

        terms = (compactness, leg_strength, pivot_quality, inclination)
        return math.prod(terms) ** (1.0 / len(terms))

    @staticmethod
    def _entry_day_index(view: MarketView, last_swing: SwingPoint) -> int | None:
        """Index of the candle that follows ``last_swing`` in the view's timeframe.

        Returns the first candle at or before the cursor whose timestamp is
        strictly after the swing point's timestamp (``None`` when that candle
        has not arrived yet — the entry day is in the future or is the swing
        candle itself). Only candles up to the cursor are inspected, so the
        gate never reads ahead.
        """
        if view.view_timeframe is None:
            series = tuple(view.store[i] for i in range(len(view.store)))
        else:
            series = view.store.get_candles(view.view_timeframe)
        for i in range(0, view.index + 1):
            if i >= len(series):
                break
            if series[i].timestamp > last_swing.timestamp:
                return i
        return None

    def _confirmation_failures(
        self,
        candle: Candle,
        direction: TrendDirection,
        last_swing: SwingPoint,
    ) -> list[str]:
        """List of confirmation-gate failures for the entry-day candle."""
        body = abs(candle.close - candle.open)
        rng = candle.high - candle.low
        body_ratio = body / rng if rng > 0 else 0.0
        bullish = direction == TrendDirection.BULLISH

        reasons: list[str] = []
        if bullish and candle.close <= candle.open:
            reasons.append(f"close {candle.close:.2f} <= open {candle.open:.2f}")
        if not bullish and candle.close >= candle.open:
            reasons.append(f"close {candle.close:.2f} >= open {candle.open:.2f}")
        if body_ratio < self._min_body_pct:
            reasons.append(f"body {body_ratio:.2f} < {self._min_body_pct:.2f}")
        if self._confirm_beyond_swing:
            beyond = (
                candle.close > last_swing.price
                if bullish
                else candle.close < last_swing.price
            )
            if not beyond:
                op = ">" if bullish else "<"
                reasons.append(
                    f"close {candle.close:.2f} not {op} swing {last_swing.price:.2f}"
                )
        return reasons
