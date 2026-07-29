from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.types import Candle
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.pattern import PullbackFact, PullbackStatus
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import SwingFact, SwingPoint, SwingType, TrendDirection, TrendFact


class FourSwingPullbackDetector(Analyzer):
    def __init__(
        self,
        max_deviation_pct: float = 0.15,
        min_swing_separation_atr: float = 0.3,
        confirmation_min_body_pct: float = 0.6,
        confirmation_min_volume_ratio: float = 1.2,
        swing_key: str = "swing",
        trend_key: str = "trend",
        atr_key: str = "atr_14",
    ) -> None:
        self._max_deviation_pct = max_deviation_pct
        self._min_swing_separation_atr = min_swing_separation_atr
        self._confirmation_min_body_pct = confirmation_min_body_pct
        self._confirmation_min_volume_ratio = confirmation_min_volume_ratio
        self._swing_key = swing_key
        self._trend_key = trend_key
        self._atr_key = atr_key

    @property
    def instance_key(self) -> str:
        return "four_swing_pullback"

    def requires(self) -> tuple[FactKey, ...]:
        return (
            FactKey(self._swing_key),
            FactKey(self._trend_key),
            FactKey(self._atr_key),
        )

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey(self.instance_key),)

    def analyze(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> AnalysisResult:
        swing_fact = facts.get(FactKey(self._swing_key))
        trend_fact = facts.get(FactKey(self._trend_key))
        atr_fact = facts.get(FactKey(self._atr_key))

        if (
            not isinstance(swing_fact, SwingFact)
            or not isinstance(trend_fact, TrendFact)
            or not isinstance(atr_fact, ATRFact)
        ):
            return self._invalidated(view, "Missing required facts")

        if trend_fact.direction == TrendDirection.NEUTRAL:
            return self._invalidated(view, "Trend is neutral")

        if atr_fact.value <= 0:
            return self._invalidated(view, "ATR is zero")

        if len(swing_fact.swings) < 4:
            return self._invalidated(view, f"Fewer than 4 swings ({len(swing_fact.swings)})")

        last_4 = swing_fact.swings[-4:]

        is_bullish = trend_fact.direction == TrendDirection.BULLISH
        pattern_valid, pattern_reason = self._check_pattern(last_4, is_bullish)

        if not pattern_valid:
            return self._invalidated(view, pattern_reason)

        swing_prices = tuple(s.price for s in last_4)
        deviation = self._check_linearity(view, last_4)

        if deviation > self._max_deviation_pct:
            evidence = (
                EvidenceEntry(
                    text=(
                        f"Pattern invalidated: deviation {deviation:.1%} exceeds "
                        f"{self._max_deviation_pct:.0%} -- choppy price action"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="FourSwingPullbackDetector",
                ),
            )
            return AnalysisResult(
                facts=(
                    PullbackFact(
                        timestamp=view.current.timestamp,
                        evidence=evidence,
                        status=PullbackStatus.INVALIDATED,
                        retracement_atr=0.0,
                        direction=trend_fact.direction,
                        swing_pattern=swing_prices,
                        deviation_pct=round(deviation, 4),
                        confirmation_strength=0.0,
                    ),
                ),
                evidence=evidence,
            )

        confirmed, strength = self._check_confirmation(view, last_4[-1], is_bullish, atr_fact.value)

        if confirmed:
            status = PullbackStatus.CONFIRMED
        else:
            status = PullbackStatus.DETECTED

        if is_bullish:
            retracement_atr = max(0, last_4[-1].price - view.current.close) / atr_fact.value
        else:
            retracement_atr = max(0, view.current.close - last_4[-1].price) / atr_fact.value

        direction_label = "bullish" if is_bullish else "bearish"

        def _swing_label(s: SwingPoint) -> str:
            if s.type == SwingType.LOW:
                return "HL" if is_bullish else "LL"
            return "HH" if is_bullish else "LH"

        swing_desc = " ".join(
            f"{_swing_label(s)}({s.price:.0f})" for s in last_4
        )

        evidence_list: list[EvidenceEntry] = [
            EvidenceEntry(
                text=f"4-swing {direction_label} pattern detected: {swing_desc}",
                level=EvidenceLevel.SIGNAL,
                source="FourSwingPullbackDetector",
            ),
            EvidenceEntry(
                text=(
                    f"Max deviation: {deviation:.1%} "
                    f"(within {self._max_deviation_pct:.0%} threshold)"
                ),
                level=EvidenceLevel.INFO,
                source="FourSwingPullbackDetector",
            ),
        ]

        if confirmed:
            body_pct = self._candle_body_pct(view.current)
            vol_ratio = self._volume_ratio(view)
            evidence_list.append(
                EvidenceEntry(
                    text=(
                        f"Confirmation: {direction_label} candle close {view.current.close:.0f} "
                        f"{'>' if is_bullish else '<'} HH/LL {last_4[-1].price:.0f}, "
                        f"body {body_pct:.0%}, volume {vol_ratio:.1f}x"
                    ),
                    level=EvidenceLevel.SIGNAL,
                    source="FourSwingPullbackDetector",
                    annotation_hint="mark_pullback_confirm",
                )
            )
        else:
            evidence_list.append(
                EvidenceEntry(
                    text="Pattern detected but not yet confirmed — waiting for confirmation candle",
                    level=EvidenceLevel.SIGNAL,
                    source="FourSwingPullbackDetector",
                    annotation_hint="mark_pullback_start",
                )
            )

        evidence_result = tuple(evidence_list)

        return AnalysisResult(
            facts=(
                PullbackFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence_result,
                    status=status,
                    retracement_atr=round(retracement_atr, 4),
                    direction=trend_fact.direction,
                    swing_pattern=swing_prices,
                    deviation_pct=round(deviation, 4),
                    confirmation_strength=round(strength, 4),
                ),
            ),
            evidence=evidence_result,
        )

    def _check_pattern(
        self, swings: tuple[SwingPoint, ...], is_bullish: bool
    ) -> tuple[bool, str]:
        if len(swings) != 4:
            return False, f"Expected 4 swings, got {len(swings)}"

        types = [s.type for s in swings]
        prices = [s.price for s in swings]

        if is_bullish:
            expected = [SwingType.LOW, SwingType.HIGH, SwingType.LOW, SwingType.HIGH]
            if types != expected:
                pat = "/".join(t.value for t in types)
                return False, f"Expected HL/HH/HL/HH pattern, got {pat}"
            if prices[2] <= prices[0]:
                return (
                    False,
                    f"Swing[2] low {prices[2]:.0f} below swing[0] low {prices[0]:.0f}"
                    f" -- not higher low",
                )
            if prices[3] <= prices[1]:
                return (
                    False,
                    f"Swing[3] high {prices[3]:.0f} below swing[1] high {prices[1]:.0f}"
                    f" -- not higher high",
                )
        else:
            expected = [SwingType.HIGH, SwingType.LOW, SwingType.HIGH, SwingType.LOW]
            if types != expected:
                pat = "/".join(t.value for t in types)
                return False, f"Expected LH/LL/LH/LL pattern, got {pat}"
            if prices[2] >= prices[0]:
                return (
                    False,
                    f"Swing[2] high {prices[2]:.0f} above swing[0] high {prices[0]:.0f}"
                    f" -- not lower high",
                )
            if prices[3] >= prices[1]:
                return (
                    False,
                    f"Swing[3] low {prices[3]:.0f} above swing[1] low {prices[1]:.0f}"
                    f" -- not lower low",
                )

        return True, ""

    def _check_linearity(
        self, view: MarketView, swings: tuple[SwingPoint, ...]
    ) -> float:
        all_candles = view.history + (view.current,)
        store_start = view.cursor - len(all_candles) + 1
        max_dev = 0.0

        for i in range(len(swings) - 1):
            s1 = swings[i]
            s2 = swings[i + 1]
            idx1 = s1.index - store_start
            idx2 = s2.index - store_start

            if idx1 < 0 or idx2 < 0 or idx1 >= len(all_candles) or idx2 >= len(all_candles):
                continue
            if idx1 == idx2:
                continue

            p1 = s1.price
            p2 = s2.price
            candle_range = 0.0
            for j in range(min(idx1, idx2), max(idx1, idx2) + 1):
                if j < len(all_candles):
                    candle_range = max(candle_range, all_candles[j].high - all_candles[j].low)
            if candle_range <= 0:
                continue

            start = min(idx1, idx2)
            end = max(idx1, idx2)
            for j in range(start + 1, end):
                if j >= len(all_candles):
                    break
                candle_close = all_candles[j].close
                t = (j - idx1) / (idx2 - idx1)
                line_price = p1 + t * (p2 - p1)
                dev = abs(candle_close - line_price) / candle_range
                if dev > max_dev:
                    max_dev = dev

        return max_dev

    def _check_confirmation(
        self,
        view: MarketView,
        last_swing: SwingPoint,
        is_bullish: bool,
        atr: float,
    ) -> tuple[bool, float]:
        current = view.current
        body_pct = self._candle_body_pct(current)
        vol_ratio = self._volume_ratio(view)

        if is_bullish:
            close_beyond = current.close > last_swing.price
        else:
            close_beyond = current.close < last_swing.price

        body_ok = body_pct >= self._confirmation_min_body_pct
        vol_ok = vol_ratio >= self._confirmation_min_volume_ratio

        if not close_beyond:
            return False, 0.0

        strength = 0.0
        if close_beyond:
            strength += 0.4
        if body_ok:
            strength += 0.3
        if vol_ok:
            strength += 0.3

        confirmed = close_beyond and body_ok and vol_ok
        return confirmed, strength

    def _candle_body_pct(self, candle: Candle) -> float:
        candle_range = candle.high - candle.low
        if candle_range <= 0:
            return 0.0
        return abs(candle.close - candle.open) / candle_range

    def _volume_ratio(self, view: MarketView) -> float:
        all_candles = view.history + (view.current,)
        if len(all_candles) < 21:
            return 1.0
        lookback = all_candles[-21:-1]
        avg_vol = sum(c.volume for c in lookback) / len(lookback) if lookback else 1.0
        if avg_vol <= 0:
            return 1.0
        return view.current.volume / avg_vol

    def _invalidated(self, view: MarketView, reason: str) -> AnalysisResult:
        evidence = (
            EvidenceEntry(
                text=f"No pullback — {reason}",
                level=EvidenceLevel.INFO,
                source="FourSwingPullbackDetector",
            ),
        )
        return AnalysisResult(
            facts=(
                PullbackFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    status=PullbackStatus.INVALIDATED,
                    retracement_atr=0.0,
                    direction=TrendDirection.NEUTRAL,
                    swing_pattern=(),
                    deviation_pct=0.0,
                    confirmation_strength=0.0,
                ),
            ),
            evidence=evidence,
        )
