from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.types import Candle, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRSeriesFact
from marketatlas.facts.structural import SwingFact, SwingPoint, SwingType

_TF_DURATION: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
    Timeframe.W1: timedelta(days=7),
}


def tf_duration(timeframe: Timeframe) -> timedelta:
    """Nominal wall-clock span one bar of ``timeframe`` covers."""
    return _TF_DURATION[timeframe]


class MagnitudeSwingAnalyzer(Analyzer):
    """Swing detector with an ATR floor on the spacing between consecutive pivots.

    ``BasicSwingAnalyzer`` is magnitude-blind: it labels a 0.16-ATR wiggle and a
    9-ATR breakout as the same object. Over Dukascopy 1d FX that is ~36 pivots
    per 100 bars, with cross-symbol median pivot travel ranging from 1.14 ATR
    (USDCAD) to 3.04 ATR (EURJPY), so any downstream pattern filter has to
    discard ~97% of candidates before it sees a tradeable move.

    This detector keeps the same strict local-extremum test but admits a pivot of
    the opposite type only once it has travelled at least ``min_travel_atr``
    ATRs from the previously kept pivot. Sub-threshold opposite pivots are
    folded back into the pivot before it (when more extreme) rather than
    emitted, which keeps the output strictly alternating *and* spaced.

    Both properties are load-bearing, and the second one is doing nearly all the
    work: on this universe a single H/L leg (no alternation, no pattern) scores
    identically to a 5-pivot pattern, because ``min_travel_atr`` already *is* the
    magnitude filter. What survives is mean reversion after large moves, not
    swing geometry.

    Causality: a pivot at index ``i`` is only known once ``right_bars`` later
    bars have closed, so detection never reads past ``right_bars - 1`` bars
    before the cursor.
    """

    def __init__(
        self,
        left_bars: int = 2,
        right_bars: int = 2,
        min_travel_atr: float = 3.0,
        atr_key: str = "atr_14_series",
        lookback: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if min_travel_atr <= 0:
            raise ValueError("min_travel_atr must be positive")
        if left_bars < 0 or right_bars < 0:
            raise ValueError("left_bars and right_bars must be non-negative")
        self._left_bars = left_bars
        self._right_bars = right_bars
        self._min_travel_atr = min_travel_atr
        self._atr_key = atr_key
        self._lookback = lookback

    @property
    def instance_key(self) -> str:
        return self._name or f"magnitude_swings_{self._min_travel_atr:g}"

    def requires(self) -> tuple[FactKey, ...]:
        return (self._make_key(self._atr_key),)

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        all_candles = view.series_through_cursor() + (view.current,)
        if self._lookback > 0:
            all_candles = all_candles[-self._lookback :]

        series = facts.get(self._make_key(self._atr_key))
        atr_by_ts: dict[Any, float] = {}
        if isinstance(series, ATRSeriesFact):
            atr_by_ts = {p.timestamp: p.value for p in series.points}
        elif series is not None:
            msg = f"expected ATRSeriesFact for {self._atr_key}, got {type(series).__name__}"
            raise TypeError(msg)

        if len(all_candles) < self._left_bars + self._right_bars + 1:
            evidence: tuple[EvidenceEntry, ...] = (
                EvidenceEntry(
                    text="Insufficient candles for swing detection",
                    level=EvidenceLevel.INFO,
                    source="MagnitudeSwingAnalyzer",
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

        raw = self._raw_pivots(all_candles)
        swings, unspaced = self._apply_magnitude_floor(all_candles, raw, atr_by_ts)

        high_count = sum(1 for s in swings if s.type == SwingType.HIGH)
        low_count = sum(1 for s in swings if s.type == SwingType.LOW)
        evidence_entries: list[EvidenceEntry] = [
            EvidenceEntry(
                text=(
                    f"Detected {len(swings)} swings with >= {self._min_travel_atr:g} ATR "
                    f"spacing ({high_count} highs, {low_count} lows); "
                    f"dropped {unspaced} of {len(raw)} raw pivots below the floor"
                ),
                level=EvidenceLevel.INFO,
                source="MagnitudeSwingAnalyzer",
            ),
        ]
        if len(swings) >= 2:
            spacings = sorted(
                abs(swings[i].price - swings[i - 1].price) for i in range(1, len(swings))
            )
            median_spacing = spacings[len(spacings) // 2]
            atr_now = self._atr_at(atr_by_ts, all_candles, swings[-1].index)
            suffix = ""
            if atr_now:
                suffix = f" = {median_spacing / atr_now:.1f} ATR"
            evidence_entries.append(
                EvidenceEntry(
                    text=(
                        f"Median pivot spacing {median_spacing:.2f} price units{suffix} "
                        f"over {len(spacings)} legs"
                    ),
                    level=EvidenceLevel.INFO,
                    source="MagnitudeSwingAnalyzer",
                )
            )
        evidence = tuple(evidence_entries)
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
    def _atr_at(
        atr_by_ts: Mapping[Any, float], candles: tuple[Candle, ...], index: int
    ) -> float | None:
        """ATR in force at bar ``index``, falling back to the most recent
        earlier point. Causal: never looks forward from the pivot."""
        if index < 0 or index >= len(candles):
            return None
        exact = atr_by_ts.get(candles[index].timestamp)
        if exact is not None:
            return exact
        for i in range(index, -1, -1):
            value = atr_by_ts.get(candles[i].timestamp)
            if value is not None:
                return value
        return None

    @staticmethod
    def _more_extreme(candidate: SwingPoint, other: SwingPoint) -> bool:
        if candidate.type == SwingType.HIGH:
            return candidate.price > other.price
        return candidate.price < other.price

    def _raw_pivots(self, candles: tuple[Candle, ...]) -> list[SwingPoint]:
        """Strict local extrema, high emitted before low on a dual-tagged bar."""
        raw: list[SwingPoint] = []
        n = len(candles)
        for i in range(self._left_bars, n - self._right_bars):
            high_i = candles[i].high
            low_i = candles[i].low
            is_peak = all(high_i > candles[i - j].high for j in range(1, self._left_bars + 1))
            is_peak = is_peak and all(
                high_i > candles[i + j].high for j in range(1, self._right_bars + 1)
            )
            if is_peak:
                raw.append(
                    SwingPoint(
                        price=high_i,
                        index=i,
                        type=SwingType.HIGH,
                        timestamp=candles[i].timestamp,
                    )
                )
            is_trough = all(low_i < candles[i - j].low for j in range(1, self._left_bars + 1))
            is_trough = is_trough and all(
                low_i < candles[i + j].low for j in range(1, self._right_bars + 1)
            )
            if is_trough:
                raw.append(
                    SwingPoint(
                        price=low_i,
                        index=i,
                        type=SwingType.LOW,
                        timestamp=candles[i].timestamp,
                    )
                )
        return raw

    def _apply_magnitude_floor(
        self,
        candles: tuple[Candle, ...],
        raw: list[SwingPoint],
        atr_by_ts: Mapping[Any, float],
    ) -> tuple[list[SwingPoint], int]:
        """Collapse raw pivots to alternating, ATR-spaced swings.

        A same-type pivot replaces the kept one when more extreme (a run of
        highs collapses to the highest of the run). An opposite-type pivot is
        kept only if it has travelled ``min_travel_atr`` ATRs; otherwise it is
        folded back into the pivot two positions back when more extreme, and the
        intervening pivot is dropped either way — once a fresher, equally
        extreme same-type pivot exists, the pivot it replaced no longer describes
        a real swing.
        """
        kept: list[SwingPoint] = []
        rejected = 0
        for pivot in raw:
            if not kept:
                kept.append(pivot)
                continue
            last = kept[-1]
            if pivot.type == last.type:
                if self._more_extreme(pivot, last):
                    kept[-1] = pivot
                else:
                    rejected += 1
                continue
            atr = self._atr_at(atr_by_ts, candles, pivot.index)
            if atr is None or atr <= 0:
                kept.append(pivot)
                continue
            if abs(pivot.price - last.price) >= self._min_travel_atr * atr:
                kept.append(pivot)
                continue
            rejected += 1
            if len(kept) >= 2 and kept[-2].type == pivot.type:
                if self._more_extreme(pivot, kept[-2]):
                    kept[-2] = pivot
                kept.pop()
        return kept, rejected
