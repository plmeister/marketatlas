from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.types import Candle
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact
from marketatlas.facts.pattern import PullbackFact, PullbackStatus
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import TrendDirection, TrendFact


class PullbackDetector(Analyzer):
    def __init__(
        self,
        min_retracement_atr: float = 0.5,
        max_retracement_atr: float = 2.0,
        swing_lookback: int = 20,
    ) -> None:
        self._min_retracement_atr = min_retracement_atr
        self._max_retracement_atr = max_retracement_atr
        self._swing_lookback = swing_lookback

    def requires(self) -> tuple[type[Fact], ...]:
        return (TrendFact, ATRFact)

    def produces(self) -> tuple[type[Fact], ...]:
        return (PullbackFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult:
        trend = facts[TrendFact]
        assert isinstance(trend, TrendFact)
        atr_fact = facts[ATRFact]
        assert isinstance(atr_fact, ATRFact)

        if trend.direction == TrendDirection.NEUTRAL or atr_fact.value <= 0:
            evidence = ("No pullback — trend is neutral or ATR is zero",)
            return AnalysisResult(
                facts=(
                    PullbackFact(
                        timestamp=view.current.timestamp,
                        evidence=evidence,
                        status=PullbackStatus.INVALIDATED,
                        retracement_atr=0.0,
                        direction=trend.direction,
                    ),
                ),
                evidence=evidence,
            )

        all_candles: tuple[Candle, ...] = view.history + (view.current,)
        lookback = min(self._swing_lookback, len(all_candles))
        window = all_candles[-lookback:]

        swing_high_price, swing_high_idx = self._find_swing_high(window)
        swing_low_price, swing_low_idx = self._find_swing_low(window)

        if swing_high_price is None or swing_low_price is None:
            evidence = ("Insufficient swing points for pullback detection",)
            return AnalysisResult(
                facts=(
                    PullbackFact(
                        timestamp=view.current.timestamp,
                        evidence=evidence,
                        status=PullbackStatus.INVALIDATED,
                        retracement_atr=0.0,
                        direction=trend.direction,
                    ),
                ),
                evidence=evidence,
            )

        current_price = view.current.close
        atr = atr_fact.value

        if trend.direction == TrendDirection.BULLISH:
            retracement_distance = swing_high_price - current_price
        else:
            retracement_distance = current_price - swing_low_price

        retracement_range = swing_high_price - swing_low_price

        if retracement_range <= 0:
            evidence = ("Swing range is zero — no pullback",)
            return AnalysisResult(
                facts=(
                    PullbackFact(
                        timestamp=view.current.timestamp,
                        evidence=evidence,
                        status=PullbackStatus.INVALIDATED,
                        retracement_atr=0.0,
                        direction=trend.direction,
                    ),
                ),
                evidence=evidence,
            )

        retracement_pct = retracement_distance / retracement_range
        retracement_atr = retracement_distance / atr

        status = self._determine_status(retracement_atr)

        evidence_parts: list[str] = [
            f"Pullback {status.value} in {trend.direction.value} trend",
            f"Retracement: {retracement_atr:.2f} ATR from swing high {swing_high_price:.2f}",
            f"Current price {current_price:.2f}, swing low {swing_low_price:.2f}",
            f"Retracement depth: {retracement_pct:.1%} of swing range",
        ]

        if status == PullbackStatus.DETECTED:
            evidence_parts.append("Waiting for reversal confirmation")
        elif status == PullbackStatus.CONFIRMED:
            evidence_parts.append("Reversal candle detected")
        elif status == PullbackStatus.INVALIDATED:
            if retracement_atr >= self._max_retracement_atr:
                evidence_parts.append("Retracement exceeds maximum — trend may be broken")
            else:
                evidence_parts.append("Retracement below minimum threshold")

        evidence_result: tuple[str, ...] = tuple(evidence_parts)

        return AnalysisResult(
            facts=(
                PullbackFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence_result,
                    status=status,
                    retracement_atr=round(retracement_atr, 4),
                    direction=trend.direction,
                ),
            ),
            evidence=evidence_result,
        )

    def _determine_status(self, retracement_atr: float) -> PullbackStatus:
        if retracement_atr >= self._max_retracement_atr:
            return PullbackStatus.INVALIDATED
        if retracement_atr >= self._min_retracement_atr:
            return PullbackStatus.DETECTED
        return PullbackStatus.INVALIDATED

    @staticmethod
    def _find_swing_high(
        candles: tuple[Candle, ...],
    ) -> tuple[float | None, int]:
        for i in range(len(candles) - 2, 0, -1):
            if candles[i].high > candles[i - 1].high and candles[i].high > candles[i + 1].high:
                return candles[i].high, i
        if len(candles) >= 2:
            best_idx = max(range(len(candles)), key=lambda i: candles[i].high)
            return candles[best_idx].high, best_idx
        return None, -1

    @staticmethod
    def _find_swing_low(
        candles: tuple[Candle, ...],
    ) -> tuple[float | None, int]:
        for i in range(len(candles) - 2, 0, -1):
            if candles[i].low < candles[i - 1].low and candles[i].low < candles[i + 1].low:
                return candles[i].low, i
        if len(candles) >= 2:
            best_idx = min(range(len(candles)), key=lambda i: candles[i].low)
            return candles[best_idx].low, best_idx
        return None, -1
