from __future__ import annotations

import math

from marketatlas.analysis.factkey import FactKey
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import (
    SRFact,
    SRLevel,
    SwingFact,
    SwingPoint,
    SwingType,
    TrendDirection,
)
from marketatlas.strategy.signals import TradeSignal, resolve_fact_key
from marketatlas.strategy.trade import TradeCandidate


def _fmt_p(value: float) -> str:
    """Magnitude-aware price formatting (mirrors JS _fmtP in models.js)."""
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


class RiskEngine:
    def __init__(
        self,
        risk_pct: float = 1.0,
        min_rr: float = 2.0,
        max_rr: float = 4.0,
        max_stop_atr: float = 3.0,
        max_hold_days: int = 10,
        avoid_srxing: bool = True,
        anchor_sr: bool = False,
        max_anchor_atr: float = 1.0,
        slippage_pct: float = 0.1,
        atr_key: str = "atr_14",
        sr_key: str = "sr",
        swing_key: str = "swing",
        swing_buffer_atr: float = 0.2,
        sr_buffer_atr: float = 0.5,
        entry_buffer_atr: float = 0.2,
        stop_swing_offset: int = 0,
        min_atr_pct: float = 0.0,
        max_atr_pct: float = 0.0,
        min_vol_ratio: float = 0.0,
        max_vol_ratio: float = 0.0,
        bindings: dict[str, str] | None = None,
    ) -> None:
        self._risk_pct = risk_pct
        self._min_rr = min_rr
        self._max_rr = max_rr
        self._max_stop_atr = max_stop_atr
        self._max_hold_days = max_hold_days
        self._avoid_srxing = avoid_srxing
        self._anchor_sr = anchor_sr
        self._max_anchor_atr = max_anchor_atr
        self._slippage_pct = slippage_pct
        self._swing_buffer_atr = swing_buffer_atr
        self._sr_buffer_atr = sr_buffer_atr
        self._entry_buffer_atr = entry_buffer_atr
        self._stop_swing_offset = max(stop_swing_offset, 0)
        self._min_atr_pct = min_atr_pct
        self._max_atr_pct = max_atr_pct
        self._min_vol_ratio = min_vol_ratio
        self._max_vol_ratio = max_vol_ratio
        self._atr_key = atr_key
        self._sr_key = sr_key
        self._swing_key = swing_key
        self._bindings = dict(bindings) if bindings else {}

    @property
    def max_hold_days(self) -> int:
        return self._max_hold_days

    def requires(self) -> tuple[FactKey, ...]:
        return (FactKey("atr_14"), FactKey("sr"), FactKey("swing"))

    def produces(self) -> tuple[FactKey, ...]:
        return ()

    def evaluate(
        self,
        signal: TradeSignal,
        facts: dict[FactKey, Fact],
        view: MarketView,
        balance: float = 1000.0,
    ) -> tuple[TradeCandidate | None, tuple[EvidenceEntry, ...]]:
        rejection: list[EvidenceEntry] = []

        # DSL-compiled risk nodes declare their inputs as explicit fact
        # references (backlog 083), compiled into ``bindings`` keyed by the
        # consumer's default key. A binding override wins; without one the
        # legacy name-convention defaults apply (YAML loader, direct
        # construction).
        atr_key = resolve_fact_key(facts, self._bindings.get("atr_14", self._atr_key))
        sr_key = resolve_fact_key(facts, self._bindings.get("sr", self._sr_key))
        swing_key = resolve_fact_key(facts, self._bindings.get("swing", self._swing_key))

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
        close_price = current.close

        # Volatility regime gate (0.0 = disabled): pullback signals in wild
        # or dead markets bleed to stop-outs regardless of direction, so band
        # ATR relative to price before committing capital (backlog: ATR band).
        atr_pct = atr_val / close_price * 100 if close_price else 0.0
        if self._min_atr_pct > 0 and atr_pct < self._min_atr_pct:
            rejection.append(
                EvidenceEntry(
                    text=(
                        f"Rejected: ATR {atr_val:.5f} ({atr_pct:.2f}% of price) "
                        f"below min {self._min_atr_pct:.2f}% — market too quiet"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)
        if self._max_atr_pct > 0 and atr_pct > self._max_atr_pct:
            rejection.append(
                EvidenceEntry(
                    text=(
                        f"Rejected: ATR {atr_val:.5f} ({atr_pct:.2f}% of price) "
                        f"above max {self._max_atr_pct:.2f}% — market too wild"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        # Volume-of-interest gate (0.0 = disabled): the pullback should break on
        # participation, not drift. Ratio is the signal candle's volume against
        # the trailing 20-candle mean; dead-candle and blow-off-candle signals
        # bleed out.
        if self._min_vol_ratio > 0 or self._max_vol_ratio > 0:
            vols = view.volumes
            hist_vols = [v_ for v_ in vols[:-1]][-20:]  # prior candles, excl current
            avg_vol = sum(hist_vols) / len(hist_vols) if hist_vols else 0.0
            if avg_vol > 0:
                vol_ratio = current.volume / avg_vol
                if self._min_vol_ratio > 0 and vol_ratio < self._min_vol_ratio:
                    rejection.append(
                        EvidenceEntry(
                            text=(
                                f"Rejected: volume {current.volume:.0f} "
                                f"({vol_ratio:.2f}x 20d avg) below min "
                                f"{self._min_vol_ratio:.2f}x — candle too quiet"
                            ),
                            level=EvidenceLevel.WARNING,
                            source="RiskEngine",
                        )
                    )
                    return None, tuple(rejection)
                if self._max_vol_ratio > 0 and vol_ratio > self._max_vol_ratio:
                    rejection.append(
                        EvidenceEntry(
                            text=(
                                f"Rejected: volume {current.volume:.0f} "
                                f"({vol_ratio:.2f}x 20d avg) above max "
                                f"{self._max_vol_ratio:.2f}x — blow-off candle"
                            ),
                            level=EvidenceLevel.WARNING,
                            source="RiskEngine",
                        )
                    )
                    return None, tuple(rejection)

        # Breakout entry (backlog: continued-trend entry). The signal fires on a
        # confirmed pullback candle; buying (bullish) requires price to push
        # above that candle's close by an ATR buffer, so the order only triggers
        # once the uptrend resumes — a real breakout, not the flat open.
        if signal.direction == TrendDirection.BULLISH:
            raw_entry = close_price + self._entry_buffer_atr * atr_val
            entry = raw_entry * (1 + self._slippage_pct / 100)
        else:
            raw_entry = close_price - self._entry_buffer_atr * atr_val
            entry = raw_entry * (1 - self._slippage_pct / 100)

        swing_fact = facts.get(swing_key) if swing_key is not None else None
        stop_anchor = self._find_stop_anchor(signal.direction, entry, atr_val, swing_fact)

        if signal.direction == TrendDirection.BULLISH:
            stop = stop_anchor - self._swing_buffer_atr * atr_val
        else:
            stop = stop_anchor + self._swing_buffer_atr * atr_val

        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            rejection.append(
                EvidenceEntry(
                    text=(
                        "Rejected: stop distance is zero "
                        f"(entry {_fmt_p(entry)}, stop {_fmt_p(stop)})"
                    ),
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
                        f"exceeds max {self._max_stop_atr:.1f} ATR "
                        f"(entry {_fmt_p(entry)}, stop {_fmt_p(stop)})"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        if self._avoid_srxing:
            hit = self._stop_crosses_sr(signal.direction, entry, stop, sr_fact.levels)
            if hit is not None:
                rejection.append(
                    EvidenceEntry(
                        text=(
                            f"Rejected: stop {_fmt_p(stop)} breaks through "
                            f"{hit.type} {_fmt_p(hit.price)} "
                            f"(entry {_fmt_p(entry)})"
                        ),
                        level=EvidenceLevel.WARNING,
                        source="RiskEngine",
                    )
                )
                return None, tuple(rejection)

        found = self._find_valid_rr(signal.direction, entry, stop_distance, sr_fact, atr_val)
        if found is None:
            blockers = self._blocking_sr(signal.direction, entry, stop_distance, sr_fact, atr_val)
            blocks = (
                ", ".join(f"{lv.type}@{_fmt_p(lv.price)}(x{lv.strength})" for lv in blockers)
                if blockers
                else "none"
            )
            rejection.append(
                EvidenceEntry(
                    text=(
                        f"Rejected: no valid RR in [{self._min_rr}, {self._max_rr}] "
                        f"without crossing S/R "
                        f"(entry {_fmt_p(entry)}, stop {_fmt_p(stop)}, "
                        f"stop {stop_distance / atr_val:.1f} ATR; "
                        f"blocking S/R: {blocks})"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        rr_ratio, _ = found
        target = (
            entry + rr_ratio * stop_distance
            if signal.direction == TrendDirection.BULLISH
            else entry - rr_ratio * stop_distance
        )

        if self._avoid_srxing and self._crosses_sr(signal.direction, entry, target, sr_fact.levels):
            crossing = [
                lv for lv in sr_fact.levels if min(entry, target) < lv.price < max(entry, target)
            ]
            crossing_desc = ", ".join(f"{lv.type} at {_fmt_p(lv.price)}" for lv in crossing)
            rejection.append(
                EvidenceEntry(
                    text=(
                        f"Rejected: S/R crossing ({crossing_desc}) "
                        f"between entry {_fmt_p(entry)} and target {_fmt_p(target)}"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                )
            )
            return None, tuple(rejection)

        anchor: SRLevel | None = None
        if self._anchor_sr:
            anchor = self._find_anchor(signal.direction, target, sr_fact.levels, atr_val)
            if anchor is None:
                rejection.append(
                    EvidenceEntry(
                        text=(
                            f"Rejected: no S/R anchor within {self._max_anchor_atr} ATR "
                            f"beyond target {_fmt_p(target)} "
                            f"(entry {_fmt_p(entry)}; "
                            f"dir {'up' if signal.direction == TrendDirection.BULLISH else 'down'})"
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
                    f"Stop: {_fmt_p(stop)} "
                    f"({stop_distance / atr_val:.1f} ATR below entry, "
                    f"beyond last swing at {_fmt_p(stop_anchor)})"
                ),
                level=EvidenceLevel.INFO,
                source="RiskEngine",
            ),
            EvidenceEntry(
                text=f"Target: {_fmt_p(target)} (RR {rr_ratio:.1f})",
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

        if self._anchor_sr:
            assert anchor is not None
            evidence.append(
                EvidenceEntry(
                    text=(
                        f"S/R anchor: {anchor.type} {_fmt_p(anchor.price)} "
                        f"({abs(anchor.price - target) / atr_val:.2f} ATR beyond target)"
                    ),
                    level=EvidenceLevel.INFO,
                    source="RiskEngine",
                ),
            )

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
            min_rr=self._min_rr,
        ), tuple(evidence)

    def _find_stop_anchor(
        self,
        direction: TrendDirection,
        entry: float,
        atr: float,
        swing_fact: Fact | None,
    ) -> float:
        if isinstance(swing_fact, SwingFact) and swing_fact.swings:
            if direction == TrendDirection.BULLISH:
                lows = [
                    s
                    for s in swing_fact.swings
                    if s.type == SwingType.LOW and s.price < entry
                ]
                anchor = self._swing_at_offset(lows, self._stop_swing_offset)
                if anchor is not None:
                    return anchor
            else:
                highs = [
                    s
                    for s in swing_fact.swings
                    if s.type == SwingType.HIGH and s.price > entry
                ]
                anchor = self._swing_at_offset(highs, self._stop_swing_offset)
                if anchor is not None:
                    return anchor

        if direction == TrendDirection.BULLISH:
            return entry - 2.0 * atr
        else:
            return entry + 2.0 * atr

    @staticmethod
    def _swing_at_offset(points: list[SwingPoint], offset: int) -> float | None:
        """Price of the swing ``offset`` places back from the most recent one.

        ``offset=0`` is the final (most recent) swing — the tightest anchor,
        closest to entry, giving the narrowest stop/target. ``offset=1`` is the
        second-most-recent (the old last-but-one choice), etc. Falls back to
        the only swing when there are fewer than ``offset + 1``.
        """
        if not points:
            return None
        ordered = sorted(points, key=lambda s: (s.index, s.timestamp))
        idx = max(0, len(ordered) - 1 - offset)
        return ordered[idx].price

    def _find_valid_rr(
        self,
        direction: TrendDirection,
        entry: float,
        stop_distance: float,
        sr_fact: SRFact,
        atr: float,
    ) -> tuple[float, tuple[SRLevel, ...]] | None:
        for rr in _frange(self._min_rr, self._max_rr + 0.001, 0.1):
            if rr <= 0:
                continue
            if direction == TrendDirection.BULLISH:
                target = entry + rr * stop_distance
            else:
                target = entry - rr * stop_distance

            if not self._avoid_srxing:
                return rr, tuple()

            bad, _ = self._target_clear(direction, entry, target, sr_fact.levels, atr)
            if not bad:
                return rr, tuple()

        return None

    def _blocking_sr(
        self,
        direction: TrendDirection,
        entry: float,
        stop_distance: float,
        sr_fact: SRFact,
        atr: float,
    ) -> tuple[SRLevel, ...]:
        """S/R levels that block every target across the RR range."""
        if not self._avoid_srxing:
            return ()
        ordered: dict[float, SRLevel] = {}
        for rr in _frange(self._min_rr, self._max_rr + 0.001, 0.1):
            if rr <= 0:
                continue
            target = (
                entry + rr * stop_distance
                if direction == TrendDirection.BULLISH
                else entry - rr * stop_distance
            )
            _, hits = self._target_clear(direction, entry, target, sr_fact.levels, atr)
            for lv in hits:
                ordered[lv.price] = lv
        return tuple(sorted(ordered.values(), key=lambda lv: lv.price))

    def _target_clear(
        self,
        direction: TrendDirection,
        entry: float,
        target: float,
        levels: tuple[SRLevel, ...],
        atr: float,
    ) -> tuple[bool, tuple[SRLevel, ...]]:
        buffer = self._sr_buffer_atr * atr
        lo, hi = min(entry, target), max(entry, target)
        hits: list[SRLevel] = []
        for level in levels:
            if lo < level.price < hi:
                hits.append(level)
                continue
            if abs(level.price - target) < buffer:
                hits.append(level)
        return bool(hits), tuple(hits)

    def _find_anchor(
        self,
        direction: TrendDirection,
        target: float,
        levels: tuple[SRLevel, ...],
        atr: float,
    ) -> SRLevel | None:
        """Return the nearest S/R level anchoring the target, or None.

        For a long the target sits below a resistance level (price turns down);
        for a short it sits above a support level (price turns up). The level
        must lie within ``_max_anchor_atr * atr`` beyond the target so the
        turn point is close enough to constrain the exit.
        """
        max_dist = self._max_anchor_atr * atr
        best: SRLevel | None = None
        best_dist = float("inf")
        for level in levels:
            if direction == TrendDirection.BULLISH:
                in_zone = level.type == "resistance" and level.price > target
            else:
                in_zone = level.type == "support" and level.price < target
            if not in_zone:
                continue
            dist = abs(level.price - target)
            if dist <= max_dist and dist < best_dist:
                best = level
                best_dist = dist
        return best

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

    def _stop_crosses_sr(
        self,
        direction: TrendDirection,
        entry: float,
        stop: float,
        levels: tuple[SRLevel, ...],
    ) -> SRLevel | None:
        """Return the S/R level the stop would break through, or None.

        For a long the stop sits below the entry; it must not be placed beneath
        a support level (that would stop out straight through the floor). For a
        short the stop sits above the entry; it must not be placed above a
        resistance level. Any such level between the stop and entry rejects the
        candidate — the stop is not clamped, the trade is refused.
        """
        for level in levels:
            if direction == TrendDirection.BULLISH:
                if level.type == "support" and stop < level.price < entry:
                    return level
            else:
                if level.type == "resistance" and entry < level.price < stop:
                    return level
        return None


def _frange(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    v = start
    while v < stop:
        values.append(round(v, 10))
        v += step
    return values
