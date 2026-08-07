from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.pattern import PullbackFact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import TrendDirection, TrendFact, SwingStructureFact, SwingType


class PullbackPatternAnalyzer(Analyzer):
    def __init__(
        self,
        swingstructure_key: str = "swing_structure",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._swingstructure_key = swingstructure_key

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
        lows = [s for s in struct.points if s.type == SwingType.LOW]
        highs = [s for s in struct.points if s.type == SwingType.HIGH]

        all_higher_lows = all(b.price > a.price for a, b in zip(lows, lows[1:]))
        all_lower_lows = all(b.price < a.price for a, b in zip(lows, lows[1:]))

        all_higher_highs = all(b.price > a.price for a, b in zip(highs, highs[1:]))
        all_lower_highs = all(b.price < a.price for a, b in zip(highs, highs[1:]))

        direction = TrendDirection.NEUTRAL
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
        evidence = (
            EvidenceEntry(
                text=f"pullback detected {direction}",
                level=EvidenceLevel.INFO,
                source="PullbackDetector",
            ),
        )
        pattern: tuple[float, ...] = ()
        if len(lows) >= 2 and len(highs) >= 2:
            pts = sorted(
                (lows[-2], lows[-1], highs[-2], highs[-1]),
                key=lambda s: s.index,
            )
            pattern = tuple(p.price for p in pts)
        return AnalysisResult(
            facts=(
                PullbackFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    direction=direction,
                    swing_pattern=pattern,
                ),
            ),
            evidence=evidence,
        )
