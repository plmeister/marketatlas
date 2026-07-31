from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import SRFact, SRLevel, SwingFact, SwingPoint


class SupportResistanceAnalyzer(Analyzer):
    def __init__(
        self,
        swing_key: str = "swing",
        atr_key: str = "atr_14",
        level_tolerance_atr: float = 0.5,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._swing_key = swing_key
        self._atr_key = atr_key
        self._level_tolerance_atr = level_tolerance_atr

    @property
    def instance_key(self) -> str:
        return "sr"

    def requires(self) -> tuple[FactKey, ...]:
        return (
            self._make_key(self._swing_key),
            self._make_key(self._atr_key),
        )

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        swing_fact = facts.get(self._make_key(self._swing_key))
        atr_fact = facts.get(self._make_key(self._atr_key))

        if not isinstance(swing_fact, SwingFact) or not swing_fact.swings:
            evidence: tuple[EvidenceEntry, ...] = (
                EvidenceEntry(
                    text="No S/R levels — no swings available",
                    level=EvidenceLevel.INFO,
                    source="SupportResistanceAnalyzer",
                ),
            )
            return AnalysisResult(
                facts=(
                    SRFact(
                        timestamp=view.current.timestamp,
                        evidence=evidence,
                        levels=(),
                    ),
                ),
                evidence=evidence,
            )

        if not isinstance(atr_fact, ATRFact) or atr_fact.value <= 0:
            evidence = (
                EvidenceEntry(
                    text="No S/R levels — ATR unavailable or zero",
                    level=EvidenceLevel.INFO,
                    source="SupportResistanceAnalyzer",
                ),
            )
            return AnalysisResult(
                facts=(
                    SRFact(
                        timestamp=view.current.timestamp,
                        evidence=evidence,
                        levels=(),
                    ),
                ),
                evidence=evidence,
            )

        tolerance = self._level_tolerance_atr * atr_fact.value
        clusters = self._cluster_swings(swing_fact.swings, tolerance)

        current_price = view.current.close
        levels: list[SRLevel] = []
        for cluster_prices in clusters:
            avg_price = sum(cluster_prices) / len(cluster_prices)
            strength = len(cluster_prices)
            level_type = "support" if avg_price < current_price else "resistance"
            levels.append(SRLevel(price=avg_price, strength=strength, type=level_type))

        levels.sort(key=lambda lv: lv.price)

        support_levels = [lv for lv in levels if lv.type == "support"]
        resistance_levels = [lv for lv in levels if lv.type == "resistance"]

        evidence_list: list[EvidenceEntry] = [
            EvidenceEntry(
                text=(
                    f"Identified {len(levels)} S/R levels: "
                    f"{len(support_levels)} support, "
                    f"{len(resistance_levels)} resistance"
                ),
                level=EvidenceLevel.INFO,
                source="SupportResistanceAnalyzer",
            ),
        ]

        if support_levels:
            nearest = support_levels[-1]
            evidence_list.append(
                EvidenceEntry(
                    text=(f"Nearest support: {nearest.price:.2f} " f"({nearest.strength} touches)"),
                    level=EvidenceLevel.SIGNAL,
                    source="SupportResistanceAnalyzer",
                ),
            )

        if resistance_levels:
            nearest = resistance_levels[0]
            evidence_list.append(
                EvidenceEntry(
                    text=(
                        f"Nearest resistance: {nearest.price:.2f} " f"({nearest.strength} touches)"
                    ),
                    level=EvidenceLevel.SIGNAL,
                    source="SupportResistanceAnalyzer",
                ),
            )

        evidence = tuple(evidence_list)
        return AnalysisResult(
            facts=(
                SRFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    levels=tuple(levels),
                ),
            ),
            evidence=evidence,
        )

    @staticmethod
    def _cluster_swings(swings: tuple[SwingPoint, ...], tolerance: float) -> list[list[float]]:
        points = sorted(
            [(s.price, s.type) for s in swings],
            key=lambda x: x[0],
        )
        if not points:
            return []

        clusters: list[list[float]] = []
        current_cluster: list[float] = [points[0][0]]

        for price, _ in points[1:]:
            if price - current_cluster[-1] <= tolerance:
                current_cluster.append(price)
            else:
                clusters.append(current_cluster)
                current_cluster = [price]

        clusters.append(current_cluster)
        return clusters
