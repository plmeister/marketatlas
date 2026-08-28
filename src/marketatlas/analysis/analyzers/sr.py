from bisect import bisect_right
from collections.abc import Callable
from datetime import datetime
from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRPoint, ATRSeriesFact
from marketatlas.facts.structural import SRFact, SRLevel, SwingFact, SwingType


class SupportResistanceAnalyzer(Analyzer):
    def __init__(
        self,
        swing_key: str = "swing",
        atr_series_key: str = "atr_14_series",
        level_tolerance_atr: float = 0.5,
        min_touches: int = 2,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._swing_key = swing_key
        self._atr_series_key = atr_series_key
        self._level_tolerance_atr = level_tolerance_atr
        self._min_touches = min_touches

    @property
    def instance_key(self) -> str:
        return "sr"

    def requires(self) -> tuple[FactKey, ...]:
        return (
            self._make_key(self._swing_key),
            self._make_key(self._atr_series_key),
        )

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        swing_fact = facts.get(self._make_key(self._swing_key))
        atr_series = facts.get(self._make_key(self._atr_series_key))

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

        if not isinstance(atr_series, ATRSeriesFact) or not atr_series.points:
            evidence = (
                EvidenceEntry(
                    text="No S/R levels — ATR series unavailable or empty",
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

        atr_lookup = _ATRLookup(atr_series.points)
        tolerance_at: Callable[[datetime], float] = lambda ts: (  # noqa: E731
            self._level_tolerance_atr * atr_lookup.at(ts)
        )

        cluster_low = self._cluster_swings(
            [
                (s.price, tolerance_at(s.timestamp))
                for s in swing_fact.swings
                if s.type == SwingType.LOW
            ]
        )
        cluster_high = self._cluster_swings(
            [
                (s.price, tolerance_at(s.timestamp))
                for s in swing_fact.swings
                if s.type == SwingType.HIGH
            ]
        )

        levels: list[SRLevel] = []
        for cluster_prices in cluster_low:
            if len(cluster_prices) < self._min_touches:
                continue
            avg_price = sum(cluster_prices) / len(cluster_prices)
            strength = len(cluster_prices)
            level_type = "support"
            levels.append(SRLevel(price=avg_price, strength=strength, type=level_type))

        for cluster_prices in cluster_high:
            if len(cluster_prices) < self._min_touches:
                continue
            avg_price = sum(cluster_prices) / len(cluster_prices)
            strength = len(cluster_prices)
            level_type = "resistance"
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
                    text=(f"Nearest support: {nearest.price:.2f} ({nearest.strength} touches)"),
                    level=EvidenceLevel.SIGNAL,
                    source="SupportResistanceAnalyzer",
                ),
            )

        if resistance_levels:
            nearest = resistance_levels[0]
            evidence_list.append(
                EvidenceEntry(
                    text=(f"Nearest resistance: {nearest.price:.2f} ({nearest.strength} touches)"),
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
    def _cluster_swings(points: list[tuple[float, float]]) -> list[list[float]]:
        """Cluster ``(price, tolerance)`` points by overlapping bands.

        Each swing occupies a band ``price ± tolerance`` sized by the ATR at
        its own candle. Swings whose bands overlap form one level. Sorting by
        price keeps the merge greedy and order-independent — a swing's band
        never shifts with the current cursor, so a pair that clusters today
        still clusters tomorrow.
        """
        clusters: list[list[float]] = []
        current_cluster: list[float] = []
        cluster_hi = float("-inf")

        for price, tolerance in sorted(points, key=lambda p: p[0]):
            band_lo = price - tolerance
            band_hi = price + tolerance
            if current_cluster and band_lo <= cluster_hi:
                current_cluster.append(price)
                cluster_hi = max(cluster_hi, band_hi)
            else:
                if current_cluster:
                    clusters.append(current_cluster)
                current_cluster = [price]
                cluster_hi = band_hi

        if current_cluster:
            clusters.append(current_cluster)
        return clusters


class _ATRLookup:
    """Timestamp → ATR lookup over a per-candle series (sorted by time).

    A query falls back to the latest series point at or before the requested
    time, and to the first point when the request predates the series.
    """

    def __init__(self, points: tuple[ATRPoint, ...]) -> None:
        self._timestamps = tuple(p.timestamp for p in points)
        self._values = tuple(p.value for p in points)

    def at(self, timestamp: datetime) -> float:
        if not self._timestamps:
            return 0.0
        idx = bisect_right(self._timestamps, timestamp)
        return self._values[idx - 1] if idx > 0 else self._values[0]
