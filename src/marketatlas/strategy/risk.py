from __future__ import annotations

from marketatlas.analysis.factkey import FactKey
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import (
    SRFact,
    SRLevel,
    SwingFact,
    SwingType,
    TrendDirection,
)
from marketatlas.strategy.signals import TradeSignal, resolve_fact_key
from marketatlas.strategy.trade import TradeCandidate


class RiskEngine:
    def __init__(
        self,
        risk_pct: float = 1.0,
        min_rr: float = 2.0,
        max_rr: float = 4.0,
        max_stop_atr: float = 3.0,
        max_hold_days: int = 10,
        avoid_srxing: bool = True,
        slippage_pct: float = 0.1,
        atr_key: str = "atr_14",
        sr_key: str = "sr",
        swing_key: str = "swing",
    ) -> None:
        self._risk_pct = risk_pct
        self._min_rr = min_rr
        self._max_rr = max_rr
        self._max_stop_atr = max_stop_atr
        self._max_hold_days = max_hold_days
        self._avoid_srxing = avoid_srxing
        self._slippage_pct = slippage_pct
        self._atr_key = atr_key
        self._sr_key = sr_key
        self._swing_key = swing_key

    @property
    def max_hold_days(self) -> int:
        return self._max_hold_days

    def evaluate(
        self,
        signal: TradeSignal,
        facts: dict[FactKey, Fact],
        view: MarketView,
        balance: float = 1000.0,
    ) -> tuple[TradeCandidate | None, tuple[EvidenceEntry, ...]]:
        rejection: list[EvidenceEntry] = []

        atr_key = resolve_fact_key(facts, self._atr_key)
        sr_key = resolve_fact_key(facts, self._sr_key)
        swing_key = resolve_fact_key(facts, self._swing_key)

        atr = facts.get(atr_key) if atr_key is not None else None
        if not isinstance(atr, ATRFact) or atr.value <= 0:
            rejection.append(
                EvidenceEntry(
                    text="Rejected: no valid ATR fact",
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        sr_fact = facts.get(sr_key) if sr_key is not None else None
        if not isinstance(sr_fact, SRFact):
            rejection.append(
                EvidenceEntry(
                    text="Rejected: no SR fact available",
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        atr_val = atr.value
        current = view.current
        open_price = current.open

        if signal.direction == TrendDirection.BULLISH:
            entry = open_price * (1 + self._slippage_pct / 100)
        else:
            entry = open_price * (1 - self._slippage_pct / 100)

        swing_fact = facts.get(swing_key) if swing_key is not None else None
        nearest_swing = self._find_nearest_swing(
            signal.direction, entry, atr_val, swing_fact
        )

        if signal.direction == TrendDirection.BULLISH:
            stop = nearest_swing - 0.2 * atr_val
        else:
            stop = nearest_swing + 0.2 * atr_val

        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            rejection.append(
                EvidenceEntry(
                    text="Rejected: stop distance is zero",
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        if stop_distance > self._max_stop_atr * atr_val:
            rejection.append(
                EvidenceEntry(
                    text=(
                        f"Rejected: stop distance {stop_distance / atr_val:.1f} ATR "
                        f"exceeds max {self._max_stop_atr:.1f} ATR"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        rr_ratio = self._find_valid_rr(
            signal.direction, entry, stop_distance, sr_fact
        )
        if rr_ratio is None:
            rejection.append(
                EvidenceEntry(
                    text=(
                        f"Rejected: no valid RR in [{self._min_rr}, {self._max_rr}] "
                        f"without crossing S/R"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        target = entry + rr_ratio * stop_distance if signal.direction == TrendDirection.BULLISH else entry - rr_ratio * stop_distance

        if self._avoid_srxing and self._crosses_sr(signal.direction, entry, target, sr_fact.levels):
            crossing = [
                lv for lv in sr_fact.levels
                if min(entry, target) < lv.price < max(entry, target)
            ]
            crossing_desc = ", ".join(
                f"{lv.type} at {lv.price:.2f}" for lv in crossing
            )
            rejection.append(
                EvidenceEntry(
                    text=(
                        f"Rejected: S/R crossing ({crossing_desc}) "
                        f"between entry {entry:.2f} and target {target:.2f}"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        risk_amount = balance * (self._risk_pct / 100)
        size = risk_amount / stop_distance
        reward_amount = rr_ratio * risk_amount

        evidence: list[EvidenceEntry] = [
            EvidenceEntry(
                text=(
                    f"Stop: {stop:.2f} "
                    f"({stop_distance / atr_val:.1f} ATR below entry, "
                    f"beyond swing at {nearest_swing:.2f})"
                ),
                level=EvidenceLevel.INFO,
                source="RiskEngine",
            ),
            EvidenceEntry(
                text=f"Target: {target:.2f} (RR {rr_ratio:.1f})",
                level=EvidenceLevel.INFO,
                source="RiskEngine",
            ),
            EvidenceEntry(
                text=(
                    f"Size: {size:.4f} "
                    f"(risk {risk_amount:.2f} at {self._risk_pct:.1f}% of {balance:.2f})"
                ),
                level=EvidenceLevel.INFO,
                source="RiskEngine",
            ),
        ]

        if self._slippage_pct > 0:
            evidence.append(
                EvidenceEntry(
                    text=f"Slippage: {self._slippage_pct:.1f}% applied to entry",
                    level=EvidenceLevel.INFO,
                    source="RiskEngine",
                ),
            )

        return TradeCandidate(
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
            evidence=tuple(evidence),
        ), tuple(evidence)

    def _find_nearest_swing(
        self,
        direction: TrendDirection,
        entry: float,
        atr: float,
        swing_fact: Fact | None,
    ) -> float:
        if isinstance(swing_fact, SwingFact) and swing_fact.swings:
            if direction == TrendDirection.BULLISH:
                lows = [s.price for s in swing_fact.swings if s.type == SwingType.LOW and s.price < entry]
                if lows:
                    return max(lows)
            else:
                highs = [s.price for s in swing_fact.swings if s.type == SwingType.HIGH and s.price > entry]
                if highs:
                    return min(highs)

        if direction == TrendDirection.BULLISH:
            return entry - 2.0 * atr
        else:
            return entry + 2.0 * atr

    def _find_valid_rr(
        self,
        direction: TrendDirection,
        entry: float,
        stop_distance: float,
        sr_fact: SRFact,
    ) -> float | None:
        for rr in _frange(self._min_rr, self._max_rr + 0.001, 0.1):
            if direction == TrendDirection.BULLISH:
                target = entry + rr * stop_distance
            else:
                target = entry - rr * stop_distance

            if not self._avoid_srxing:
                return rr

            if not self._crosses_sr(direction, entry, target, sr_fact.levels):
                return rr

        return None

    def _crosses_sr(
        self,
        direction: TrendDirection,
        entry: float,
        target: float,
        levels: tuple[SRLevel, ...],
    ) -> bool:
        lo, hi = min(entry, target), max(entry, target)
        for level in levels:
            if lo < level.price < hi:
                return True
        return False


def _frange(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    v = start
    while v < stop:
        values.append(round(v, 10))
        v += step
    return values
