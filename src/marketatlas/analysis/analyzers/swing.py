from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.types import Candle
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import SwingFact, SwingPoint, SwingType


class SwingStructureAnalyzer(Analyzer):
    def __init__(
        self,
        lookback: int = 20,
        min_swing_atr: float = 0.3,
        atr_key: str = "atr_14",
    ) -> None:
        self._lookback = lookback
        self._min_swing_atr = min_swing_atr
        self._atr_key = atr_key

    @property
    def instance_key(self) -> str:
        return "swing"

    def requires(self) -> tuple[FactKey, ...]:
        return (FactKey(self._atr_key),)

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        atr_fact = facts.get(FactKey(self._atr_key))
        if not isinstance(atr_fact, ATRFact) or atr_fact.value <= 0:
            evidence: tuple[EvidenceEntry, ...] = (
                EvidenceEntry(
                    text="No swings detected — ATR unavailable or zero",
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

        all_candles: tuple[Candle, ...] = view.history + (view.current,)
        lookback = min(self._lookback, len(all_candles))
        window = all_candles[-lookback:]

        if len(window) < 3:
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

        raw = self._find_raw_swings(window, view.cursor - lookback)
        filtered = self._filter_alternating(raw)
        separated = self._filter_atr_separation(filtered, atr_fact.value)
        separated = self._filter_alternating(separated)

        high_count = sum(1 for s in separated if s.type == SwingType.HIGH)
        low_count = sum(1 for s in separated if s.type == SwingType.LOW)
        filtered_count = len(raw) - len(filtered)
        atr_filtered = len(filtered) - len(separated)

        evidence_list: list[EvidenceEntry] = [
            EvidenceEntry(
                text=(
                    f"Detected {len(separated)} swing points in window "
                    f"({high_count} highs, {low_count} lows)"
                ),
                level=EvidenceLevel.INFO,
                source="SwingStructureAnalyzer",
            ),
        ]

        if filtered_count > 0:
            evidence_list.append(
                EvidenceEntry(
                    text=f"Removed {filtered_count} consecutive same-type swings",
                    level=EvidenceLevel.INFO,
                    source="SwingStructureAnalyzer",
                ),
            )

        if atr_filtered > 0:
            evidence_list.append(
                EvidenceEntry(
                    text=(
                        f"Filtered {atr_filtered} swings below minimum "
                        f"{self._min_swing_atr} ATR separation"
                    ),
                    level=EvidenceLevel.INFO,
                    source="SwingStructureAnalyzer",
                ),
            )

        if separated:
            prices = [s.price for s in separated]
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
                    swings=tuple(separated),
                ),
            ),
            evidence=evidence,
        )

    @staticmethod
    def _find_raw_swings(candles: tuple[Candle, ...], base_index: int) -> list[SwingPoint]:
        raw: list[SwingPoint] = []
        for i in range(1, len(candles) - 1):
            if candles[i].high > candles[i - 1].high and candles[i].high > candles[i + 1].high:
                raw.append(
                    SwingPoint(
                        price=candles[i].high,
                        index=base_index + i,
                        type=SwingType.HIGH,
                        timestamp=candles[i].timestamp,
                    )
                )
            elif candles[i].low < candles[i - 1].low and candles[i].low < candles[i + 1].low:
                raw.append(
                    SwingPoint(
                        price=candles[i].low,
                        index=base_index + i,
                        type=SwingType.LOW,
                        timestamp=candles[i].timestamp,
                    )
                )
        return raw

    @staticmethod
    def _filter_alternating(swings: list[SwingPoint]) -> list[SwingPoint]:
        if not swings:
            return []
        result: list[SwingPoint] = []
        last_type: SwingType | None = None
        for swing in swings:
            if last_type is None:
                result.append(swing)
                last_type = swing.type
            elif swing.type != last_type:
                result.append(swing)
                last_type = swing.type
            else:
                if swing.type == SwingType.HIGH:
                    if swing.price > result[-1].price:
                        result[-1] = swing
                else:
                    if swing.price < result[-1].price:
                        result[-1] = swing
        return result

    def _filter_atr_separation(self, swings: list[SwingPoint], atr: float) -> list[SwingPoint]:
        if not swings:
            return []
        min_sep = self._min_swing_atr * atr
        result: list[SwingPoint] = []
        last_high_price: float | None = None
        last_low_price: float | None = None
        for swing in swings:
            if swing.type == SwingType.HIGH:
                if last_high_price is not None and abs(swing.price - last_high_price) < min_sep:
                    continue
                result.append(swing)
                last_high_price = swing.price
            else:
                if last_low_price is not None and abs(swing.price - last_low_price) < min_sep:
                    continue
                result.append(swing)
                last_low_price = swing.price
        return result
