from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.types import Candle
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.structural import SwingFact, SwingPoint, SwingType


class BasicSwingAnalyzer(Analyzer):
    def __init__(
        self,
        lookback: int = 20,
        left_bars: int = 2,
        right_bars: int = 1,
        enforce_alternation: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._lookback = lookback
        self._left_bars = left_bars
        self._right_bars = right_bars
        self._enforce_alternation = enforce_alternation

    @property
    def instance_key(self) -> str:
        return self._name or "swing"

    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        all_candles: tuple[Candle, ...] = view.series_through_cursor() + (view.current,)

        if len(all_candles) < self._left_bars + self._right_bars + 1:
            evidence: tuple[EvidenceEntry, ...] = (
                EvidenceEntry(
                    text="Insufficient candles for swing detection",
                    level=EvidenceLevel.INFO,
                    source="SwingStructureAnalyzer",
                ),
            )
            return AnalysisResult(
                facts=(
                    SwingFact(
                        timestamp=view.current.timestamp,
                        evidence=evidence,
                        swings=(),
                    ),
                ),
                evidence=evidence,
            )

        swings = self._find_raw_swings(
            all_candles,
            0,
            self._left_bars,
            self._right_bars,
            self._lookback,
            self._enforce_alternation,
        )

        high_count = sum(1 for s in swings if s.type == SwingType.HIGH)
        low_count = sum(1 for s in swings if s.type == SwingType.LOW)

        evidence_list: list[EvidenceEntry] = [
            EvidenceEntry(
                text=(
                    f"Detected {len(swings)} swing points in window "
                    f"({high_count} highs, {low_count} lows)"
                ),
                level=EvidenceLevel.INFO,
                source="BasicSwingAnalyzer",
            ),
        ]

        if swings:
            prices = [s.price for s in swings]
            evidence_list.append(
                EvidenceEntry(
                    text=f"Swing range: {min(prices):.2f} to {max(prices):.2f}",
                    level=EvidenceLevel.INFO,
                    source="SwingStructureAnalyzer",
                ),
            )

        evidence = tuple(evidence_list)
        return AnalysisResult(
            facts=(
                SwingFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    swings=tuple(swings),
                ),
            ),
            evidence=evidence,
        )

    @staticmethod
    def _find_raw_swings(
        candles: tuple[Candle, ...],
        base_index: int,
        left_bars: int = 2,
        right_bars: int = 1,
        lookback: int = 20,
        enforce_alternation: bool = False,
    ) -> list[SwingPoint]:
        raw: list[SwingPoint] = []
        n = len(candles)
        lookback_start = max(left_bars, n - lookback)
        for i in range(lookback_start, n - right_bars):
            high_i = candles[i].high
            low_i = candles[i].low

            is_peak = all(high_i > candles[i - j].high for j in range(1, left_bars + 1)) and all(
                high_i > candles[i + j].high for j in range(1, right_bars + 1)
            )

            # A bar can satisfy both tests at once: an outside bar whose high
            # exceeds every neighbour's high and whose low is below every
            # neighbour's low is simultaneously a local high and a local low.
            # Emitting only the high (the old ``continue``) discarded a real
            # claim and skewed the pivot set against wide-range bars -- the
            # largest moves in the sample. Both claims are emitted, high first
            # so the order within a bar is deterministic. Consumers that
            # require strictly increasing indices should collapse first; note
            # that ``enforce_alternation`` yields a valid alternating sequence
            # either way, and a dual-tagged bar produces a zero-duration leg.
            if is_peak:
                raw.append(
                    SwingPoint(
                        price=high_i,
                        index=base_index + i,
                        type=SwingType.HIGH,
                        timestamp=candles[i].timestamp,
                    )
                )

            is_trough = all(low_i < candles[i - j].low for j in range(1, left_bars + 1)) and all(
                low_i < candles[i + j].low for j in range(1, right_bars + 1)
            )

            if is_trough:
                raw.append(
                    SwingPoint(
                        price=low_i,
                        index=base_index + i,
                        type=SwingType.LOW,
                        timestamp=candles[i].timestamp,
                    )
                )
        if enforce_alternation:
            raw = BasicSwingAnalyzer._collapse_to_alternating(raw)
        return raw

    @staticmethod
    def _collapse_to_alternating(raw: list[SwingPoint]) -> list[SwingPoint]:
        """Reduce raw pivots to a strictly alternating high/low sequence.

        A pivot of the same type as the previously kept pivot replaces it when
        it is more extreme (higher high / lower low), so a run of consecutive
        highs collapses to the highest of the run. Strict local-extremum tests
        emit such runs whenever the neighbourhood is wide relative to the swing
        structure — e.g. left/right 48/24 on 1h bars, where every push in a
        trend is a new local high. Consumers (``swingstructure``) require an
        alternating pattern, so without this a coarse neighbourhood yields no
        structure at all instead of the intended coarse swings.
        """
        alternating: list[SwingPoint] = []
        for swing in raw:
            if alternating and alternating[-1].type == swing.type:
                previous = alternating[-1]
                more_extreme = (
                    swing.price > previous.price
                    if swing.type == SwingType.HIGH
                    else swing.price < previous.price
                )
                if more_extreme:
                    alternating[-1] = swing
                continue
            alternating.append(swing)
        return alternating
