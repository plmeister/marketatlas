from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import TrendDirection, TrendFact


class TrendAnalyzer(Analyzer):
    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
    ) -> None:
        self._fast_period = fast_period
        self._slow_period = slow_period

    def requires(self) -> tuple[type[Fact], ...]:
        return ()

    def produces(self) -> tuple[type[Fact], ...]:
        return (TrendFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult:
        prices = view.prices
        fast_ema = self._compute_ema(prices, self._fast_period)
        slow_ema = self._compute_ema(prices, self._slow_period)

        if fast_ema > slow_ema:
            direction = TrendDirection.BULLISH
        elif fast_ema < slow_ema:
            direction = TrendDirection.BEARISH
        else:
            direction = TrendDirection.NEUTRAL

        atr_value = 0.0
        atr_fact = facts.get(ATRFact)
        if atr_fact is not None and isinstance(atr_fact, ATRFact):
            atr_value = atr_fact.value

        spread = abs(fast_ema - slow_ema)
        if atr_value > 0:
            strength = min(1.0, spread / atr_value)
        else:
            price = view.current.close
            strength = min(1.0, spread / price) if price > 0 else 0.0

        price = view.current.close
        above_both = price > fast_ema and price > slow_ema
        below_both = price < fast_ema and price < slow_ema

        cmp = ">" if fast_ema > slow_ema else "<"
        evidence_parts: list[str] = [
            f"Trend: {direction.value.title()} — "
            f"EMA{self._fast_period} ({fast_ema:.2f}) {cmp} "
            f"EMA{self._slow_period} ({slow_ema:.2f})",
            f"Strength: {strength:.2f} — spread {spread:.2f}",
        ]
        if above_both:
            evidence_parts.append("Confirmed by price above both EMAs")
        elif below_both:
            evidence_parts.append("Confirmed by price below both EMAs")

        evidence = tuple(evidence_parts)

        return AnalysisResult(
            facts=(
                TrendFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    direction=direction,
                    strength=round(strength, 4),
                ),
            ),
            evidence=evidence,
        )

    @staticmethod
    def _compute_ema(prices: tuple[float, ...], period: int) -> float:
        if not prices:
            return 0.0
        period = min(period, len(prices))
        if period < 2:
            return prices[-1]
        k = 2.0 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = price * k + ema * (1 - k)
        return ema
