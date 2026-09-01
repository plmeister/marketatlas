from __future__ import annotations

from marketatlas.analysis.factkey import FactKey
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.channel import ChannelFact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import TrendDirection, TrendFact
from marketatlas.strategy.signals import (
    Signal,
    SignalEvaluation,
    TradeSignal,
    resolve_fact_key,
)


class BreakoutSignal(Signal):
    """Range-breakout entry: close pierces the trailing channel with a
    compressing range (quiet before the break) and aligned trend.

    The channel event and the pullback retracement are disjoint by
    construction: a close above the N-day high cannot coincide with a fresh
    retracement into that same range, so the two strategies partition the same
    instrument's entry opportunities instead of competing for the lane.
    """

    def __init__(
        self,
        channel_key: str = "channel_20",
        trend_key: str = "trend",
        atr_key: str = "atr_14",
        min_breakout_days: int = 0,
        compress_days: int = 10,
        compression_atr: float = 3.0,
        require_trend: bool = True,
        bindings: dict[str, str] | None = None,
    ) -> None:
        self._channel_key = channel_key
        self._trend_key = trend_key
        self._atr_key = atr_key
        self._min_breakout_days = min_breakout_days
        self._compress_days = compress_days
        self._compression_atr = compression_atr
        self._require_trend = require_trend
        self._bindings = dict(bindings) if bindings else {}

    def requires(self) -> tuple[FactKey, ...]:
        return (FactKey(self._channel_key), FactKey(self._trend_key), FactKey(self._atr_key))

    def evaluate(self, view: MarketView, facts: dict[FactKey, Fact]) -> TradeSignal | None:
        return self._evaluate(view, facts).signal

    def evaluate_with_rejections(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> SignalEvaluation:
        return self._evaluate(view, facts)

    def _evaluate(self, view: MarketView, facts: dict[FactKey, Fact]) -> SignalEvaluation:
        channel_key = resolve_fact_key(facts, self._bindings.get("channel_20", self._channel_key))
        trend_key = resolve_fact_key(facts, self._bindings.get("trend", self._trend_key))
        atr_key = resolve_fact_key(facts, self._bindings.get("atr_14", self._atr_key))

        channel = facts.get(channel_key) if channel_key is not None else None
        trend = facts.get(trend_key) if trend_key is not None else None
        atr = facts.get(atr_key) if atr_key is not None else None

        if not isinstance(channel, ChannelFact):
            return SignalEvaluation()
        if not isinstance(trend, TrendFact):
            return SignalEvaluation()
        if not isinstance(atr, ATRFact):
            return SignalEvaluation()

        current = view.current
        close = current.close

        if close > channel.high:
            direction = TrendDirection.BULLISH
            bound = channel.high
        elif close < channel.low:
            direction = TrendDirection.BEARISH
            bound = channel.low
        else:
            return SignalEvaluation()

        if not self._recent_break(channel):
            return self._rejected("breakout too old to act on")

        if self._require_trend and trend.direction != direction:
            return self._rejected(
                f"trend {trend.direction.value} opposes breakout {direction.value}"
            )

        atr_val = atr.value if atr.value > 0 else 0.0
        if not self._range_compressed(view, channel, atr_val):
            return self._rejected("range not compressed before breakout")

        buffer = 0.5 * atr_val
        entry_zone = (close - buffer, close + buffer)

        evidence = (
            EvidenceEntry(
                text=(
                    f"Signal: {direction.value} breakout above/below "
                    f"channel {channel.period}d {bound:.2f}, "
                    f"breakout age {channel.breakout_days}d"
                ),
                level=EvidenceLevel.SIGNAL,
                source="BreakoutSignal",
            ),
            EvidenceEntry(
                text=(f"Entry zone: {entry_zone[0]:.0f}\u2013{entry_zone[1]:.0f}"),
                level=EvidenceLevel.INFO,
                source="BreakoutSignal",
            ),
        )
        return SignalEvaluation(
            signal=TradeSignal(
                direction=direction,
                entry_zone=entry_zone,
                confidence=1.0,
                source="BreakoutSignal",
                evidence=evidence,
            )
        )

    def _recent_break(self, channel: ChannelFact) -> bool:
        """The break must be fresh, not stale structure that separated days ago."""
        return channel.breakout_days <= self._min_breakout_days

    def _range_compressed(
        self, view: MarketView, channel: ChannelFact, atr_val: float
    ) -> bool:
        """Require the pre-break range to be tight (≤ compression_atr × ATR).

        A clean range break usually follows compression; a breakout busting out
        of an already-wide range is often a continuation that pullback would
        have caught instead.
        """
        if atr_val <= 0 or self._compression_atr <= 0:
            return False
        recent_highs = view.highs[-self._compress_days :] if self._compress_days else ()
        recent_lows = view.lows[-self._compress_days :]
        if not recent_highs:
            return False
        span = max(recent_highs) - min(recent_lows)
        return span <= self._compression_atr * atr_val

    def _rejected(self, reason: str) -> SignalEvaluation:
        return SignalEvaluation(
            rejections=(
                EvidenceEntry(
                    text=f"Rejected: {reason}",
                    level=EvidenceLevel.WARNING,
                    source="BreakoutSignal",
                ),
            )
        )
