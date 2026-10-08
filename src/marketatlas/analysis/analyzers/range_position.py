from typing import Any

from marketatlas.analysis.analyzers.swing_magnitude import tf_duration
from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.types import Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.structural import RangePositionFact, SwingFact


class RangePositionAnalyzer(Analyzer):
    """Locate the latest swing inside the trailing range of a higher timeframe.

    Reads the most recent *completed* higher-timeframe bars and reports where the
    latest swing's price sits between their high and low. This is the one
    variable in the detector study that separated winners from losers: taking a
    short at a swing high that has broken above the trailing 12-week range scores
    about +0.19 ATR, while the same trade taken inside the range is clearly
    profitable. Fading a breakout is the losing case; fading within-range
    extremes is not.

    Completeness, not availability, is the subtlety. A weekly bar stamped Monday
    ``d`` covers ``[d, d+7)`` and is only finished at ``d+7``; reading the bar
    that merely *contains* the current daily bar is lookahead and manufactures
    the effect. So a higher-timeframe bar is usable only once
    ``stamp + duration + confirmation_lag <= current daily timestamp``.

    ``confirmation_lag`` is in extra bars of that timeframe. A bare range read
    needs ``0``. The validated measurement used ``2``, because it was derived
    from a weekly *pivot* state needing two weekly bars of confirmation, not from
    the range read itself — so ``0`` and ``2`` are both defensible and they
    measure different things. The default preserves the studied parameterisation.
    """

    def __init__(
        self,
        swing_key: str = "magnitude_swings_3.5",
        higher_timeframe: str = "1w",
        range_bars: int = 12,
        confirmation_lag: int = 2,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if range_bars < 1:
            raise ValueError("range_bars must be at least 1")
        if confirmation_lag < 0:
            raise ValueError("confirmation_lag must be non-negative")
        self._swing_key = swing_key
        self._higher_timeframe = Timeframe(higher_timeframe)
        self._range_bars = range_bars
        self._confirmation_lag = confirmation_lag

    @property
    def instance_key(self) -> str:
        return self._name or f"range_position_{self._higher_timeframe.value}_{self._range_bars}"

    def requires(self) -> tuple[FactKey, ...]:
        return (self._make_key(self._swing_key),)

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        swing_fact = facts.get(self._make_key(self._swing_key))
        reference: float | None = None
        if isinstance(swing_fact, SwingFact) and swing_fact.swings:
            reference = swing_fact.swings[-1].price
        elif swing_fact is None:
            reference = view.current.close

        higher = self._higher_view(view)
        lag = tf_duration(self._higher_timeframe) * (1 + self._confirmation_lag)
        cutoff = view.current.timestamp - lag

        # ``series_through_cursor`` is exclusive of the cursor bar, and ``select``
        # puts the cursor ON the higher-timeframe bar at-or-before "now" — which
        # is exactly the bar under test. Re-add it so completeness filtering, not
        # an off-by-one, decides what is readable.
        completed = higher.series_through_cursor() + (higher.current,)
        usable = tuple(c for c in completed if c.timestamp <= cutoff)[-self._range_bars :]

        if not usable or reference is None:
            reason = (
                f"No {self._higher_timeframe.value} bar has completed yet "
                f"(lag {self._confirmation_lag} bars)"
                if not usable
                else "No swing available for a reference price"
            )
            evidence: tuple[EvidenceEntry, ...] = (
                EvidenceEntry(
                    text=f"Range position unavailable: {reason}",
                    level=EvidenceLevel.INFO,
                    source="RangePositionAnalyzer",
                ),
            )
            return AnalysisResult(
                facts=(
                    RangePositionFact(
                        timestamp=view.current.timestamp,
                        evidence=evidence,
                        high=0.0,
                        low=0.0,
                        position=None,
                    ),
                ),
                evidence=evidence,
            )

        high = max(c.high for c in usable)
        low = min(c.low for c in usable)
        span = high - low
        position = ((reference - low) / span) if span > 0 else None

        entries: list[EvidenceEntry] = [
            EvidenceEntry(
                text=(
                    f"Range position {position:.2f} of trailing "
                    f"{self._range_bars}x{self._higher_timeframe.value} range "
                    f"({low:.2f} - {high:.2f})"
                )
                if position is not None
                else (
                    f"Trailing {self._range_bars}x{self._higher_timeframe.value} range is "
                    f"flat at {low:.2f}; position undefined"
                ),
                level=EvidenceLevel.INFO,
                source="RangePositionAnalyzer",
            ),
        ]
        if position is not None and position > 1.0:
            entries.append(
                EvidenceEntry(
                    text=(
                        f"Price {reference:.2f} is above the range high — breakout, not "
                        f"an in-range extreme"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="RangePositionAnalyzer",
                )
            )
        evidence = tuple(entries)
        return AnalysisResult(
            facts=(
                RangePositionFact(
                    timestamp=view.current.timestamp,
                    evidence=evidence,
                    high=high,
                    low=low,
                    position=position,
                ),
            ),
            evidence=evidence,
        )

    def _higher_view(self, view: MarketView) -> MarketView:
        if self._higher_timeframe not in view.store:
            msg = (
                f"RangePositionAnalyzer needs {self._higher_timeframe.value} data; "
                f"store only carries {sorted(tf.value for tf in view.store.available_timeframes)}"
            )
            raise ValueError(msg)
        return view.select(self._higher_timeframe, window_size=self._range_bars + 8)
