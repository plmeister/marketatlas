from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.types import Candle
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.structural import SwingFact, SwingPoint, SwingType


class SwingStructureAnalyzer(Analyzer):
    def __init__(
        self,
        lookback: int = 20,
        min_swing_atr: float = 0.3,
        atr_key: str = "atr_14",
        left_bars: int = 2,
        right_bars: int = 1,
    ) -> None:
        self._lookback = lookback
        self._min_swing_atr = min_swing_atr
        self._atr_key = atr_key
        self._left_bars = left_bars
        self._right_bars = right_bars

    @property
    def instance_key(self) -> str:
        return "swing"

    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        all_candles: tuple[Candle, ...] = tuple(view.store.slice(0, view.cursor)) + (view.current,)

        if len(all_candles) < self._left_bars + self._right_bars + 1:
            evidence = (
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

        swings = self._find_raw_swings(all_candles, 0, self._left_bars, self._right_bars)

        high_count = sum(1 for s in swings if s.type == SwingType.HIGH)
        low_count = sum(1 for s in swings if s.type == SwingType.LOW)

        evidence_list: list[EvidenceEntry] = [
            EvidenceEntry(
                text=(
                    f"Detected {len(swings)} swing points in window "
                    f"({high_count} highs, {low_count} lows)"
                ),
                level=EvidenceLevel.INFO,
                source="SwingStructureAnalyzer",
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
    ) -> list[SwingPoint]:
        raw: list[SwingPoint] = []
        n = len(candles)
        for i in range(left_bars, n - right_bars):
            high_i = candles[i].high
            low_i = candles[i].low

            is_peak = all(
                high_i > candles[i - j].high for j in range(1, left_bars + 1)
            ) and all(
                high_i > candles[i + j].high for j in range(1, right_bars + 1)
            )

            if is_peak:
                raw.append(
                    SwingPoint(
                        price=high_i,
                        index=base_index + i,
                        type=SwingType.HIGH,
                        timestamp=candles[i].timestamp,
                    )
                )
                continue

            is_trough = all(
                low_i < candles[i - j].low for j in range(1, left_bars + 1)
            ) and all(
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
        return raw




