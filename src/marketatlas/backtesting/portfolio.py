from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from marketatlas.analysis.ast.instrument import InstrumentBacktestResult
from marketatlas.data.instrument import Instrument
from marketatlas.data.store import MarketStore
from marketatlas.data.view import MarketView
from marketatlas.evidence.collector import EvidenceCollector
from marketatlas.evidence.model import EvidenceEntry
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.frames.store import FrameStore
from marketatlas.strategy.tradebook import TradeBook

if TYPE_CHECKING:
    from marketatlas.analysis.factkey import FactKey
    from marketatlas.backtesting.backtester import BundleProtocol
    from marketatlas.facts.base import Fact
    from marketatlas.strategy.signals import TradeSignal


@dataclass(frozen=True)
class PortfolioBacktestResult:
    """Complete portfolio backtest output, safe to pickle for later inspection.

    ``tradebook`` is the single book shared across every instrument (075);
    ``frames`` maps each instrument's canonical name to its own ``FrameStore``.
    """

    instruments: tuple[Instrument, ...]
    frames: dict[str, FrameStore]
    tradebook: TradeBook
    window_size: int
    max_hold_days: int

    @property
    def by_instrument(self) -> tuple[InstrumentBacktestResult, ...]:
        """Per-instrument results (063) over the shared book and frames."""
        return tuple(
            InstrumentBacktestResult(
                instrument=inst,
                frames=self.frames[inst.canonical],
                tradebook=self.tradebook,
            )
            for inst in self.instruments
        )


@dataclass
class _CursorEvaluation:
    instrument: Instrument
    view: MarketView
    facts: dict[FactKey, Fact]
    evidence: tuple[EvidenceEntry, ...]
    emitted: list[tuple[str, TradeSignal]]
    risk_evidence: tuple[EvidenceEntry, ...] = ()
    signal_rejections: tuple[EvidenceEntry, ...] = ()


class PortfolioBacktester:
    """Run a strategy bundle across a portfolio with one shared tradebook (075).

    The primary-timeframe timestamps of every instrument are unioned into one
    ascending calendar; ``window_size`` applies to that merged axis. At each
    cursor every instrument aligns to its latest candle at-or-before the cursor
    timestamp (``MarketStore.timestamp_index``, the same lookup 045's
    ``MarketView.select`` uses) and only re-evaluates when that candle advances,
    so each instrument records one frame per candle — mirroring the
    single-instrument replay semantics while riding the merged timeline.

    Exactly one open trade is allowed across the whole portfolio. When the book
    is free the first eligible signal in deterministic order — strategy
    priority, then instrument order — fills; all others are skipped while the
    book is busy. Open-trade fill/resolution always uses the position's own
    instrument candles; exit prices and stops never come from another
    instrument. Nothing after the cursor's aligned candle per instrument is ever
    consulted.
    """

    def __init__(
        self,
        bundle: BundleProtocol,
        instruments: Sequence[tuple[Instrument, MarketStore]],
        window_size: int = 100,
        max_hold_days: int = 10,
    ) -> None:
        self._bundle = bundle
        self._pairs = tuple(instruments)
        if not self._pairs:
            raise ValueError("At least one (instrument, store) pair is required")
        self._window_size = window_size
        self._max_hold_days = max_hold_days
        self._store_by = {inst.canonical: store for inst, store in self._pairs}
        self._merged = self._merge_calendars()
        self._position: Instrument | None = None
        self._pending_ts: datetime | None = None

    def _merge_calendars(self) -> tuple[datetime, ...]:
        """Union of primary-timeframe timestamps, sorted ascending."""
        return tuple(
            sorted({ts for _, store in self._pairs for ts in store.timestamps})
        )

    @property
    def frame_count(self) -> int:
        return max(0, len(self._merged) - self._window_size)

    def run(self) -> PortfolioBacktestResult:
        return self.run_with_progress(None)

    def run_with_progress(
        self,
        callback: Callable[[int, int], None] | None = None,
    ) -> PortfolioBacktestResult:
        frame_stores = {inst.canonical: FrameStore() for inst, _ in self._pairs}
        tradebook = self._bundle.tradebook
        self._position = None
        self._pending_ts = None
        aligned_at: dict[str, int] = {}
        total = self.frame_count

        for i, cursor_ts in enumerate(self._merged[self._window_size :]):
            self._fill_and_resolve(cursor_ts, tradebook)

            free = tradebook.has_no_open_trade and not tradebook.has_pending_order
            evaluations: list[_CursorEvaluation] = []
            for instrument, store in self._pairs:
                aligned = store.timestamp_index(cursor_ts)
                if aligned < 0:
                    continue
                if aligned == aligned_at.get(instrument.canonical):
                    continue
                aligned_at[instrument.canonical] = aligned
                view = MarketView(store, aligned, self._window_size)
                facts, loose = self._bundle.graph.run_with_evidence(view)
                evidence = self._collect_evidence(facts) + loose
                emitted, signal_rejections = self._bundle.evaluate_all_with_rejections(
                    view, facts
                )
                rejection_entries = tuple(
                    e for _, sig in signal_rejections for e in sig.rejections
                )
                evaluations.append(
                    _CursorEvaluation(
                        instrument=instrument,
                        view=view,
                        facts=facts,
                        evidence=evidence,
                        emitted=emitted,
                        signal_rejections=rejection_entries,
                    )
                )

            if free:
                self._try_submit(tradebook, evaluations)

            for ev in evaluations:
                frame_stores[ev.instrument.canonical].append(
                    AnalysisFrame(
                        timestamp=ev.view.current.timestamp,
                        candle=ev.view.current,
                        facts=dict(ev.facts),
                        evidence=ev.evidence,
                        signals=tuple(signal for _, signal in ev.emitted),
                        risk_evidence=ev.risk_evidence,
                        signal_rejections=ev.signal_rejections,
                    )
                )

            if callback is not None:
                callback(i + 1, total)

        if not tradebook.has_no_open_trade:
            position = self._position
            if position is not None:
                store = self._store_by[position.canonical]
                tradebook.close_trade(store[-1].close, store[-1].timestamp)

        return PortfolioBacktestResult(
            instruments=tuple(inst for inst, _ in self._pairs),
            frames=frame_stores,
            tradebook=tradebook,
            window_size=self._window_size,
            max_hold_days=self._max_hold_days,
        )

    def _fill_and_resolve(self, cursor_ts: datetime, tradebook: TradeBook) -> None:
        """Fill/resolve the position against its own instrument's candle.

        A pending order fills at the first candle of the position's instrument
        strictly newer than the signal candle (next-bar entry, matching the
        single-instrument replay); an open trade resolves at that instrument's
        aligned candle each cursor. Repeated resolution on a non-advancing
        candle is a no-op — a stop/target/hold close can only fire once.
        """
        position = self._position
        if position is None:
            return
        store = self._store_by[position.canonical]
        aligned = store.timestamp_index(cursor_ts)
        if aligned < 0:
            return
        candle = store[aligned]
        if tradebook.has_pending_order:
            pending_ts = self._pending_ts
            if pending_ts is not None and candle.timestamp > pending_ts:
                tradebook.fill_order(candle.open, candle.timestamp)
        if not tradebook.has_no_open_trade:
            tradebook.resolve_at_cursor(candle, self._max_hold_days)
        if tradebook.has_no_open_trade and not tradebook.has_pending_order:
            self._position = None

    def _try_submit(
        self,
        tradebook: TradeBook,
        evaluations: list[_CursorEvaluation],
    ) -> None:
        """Submit the first eligible signal: strategy priority, then instrument."""
        for strategy in self._bundle.strategies:
            for ev in evaluations:
                for name, signal in ev.emitted:
                    if name != strategy:
                        continue
                    risk_engine = self._bundle.get_risk_engine(name)
                    candidate, ev.risk_evidence = risk_engine.evaluate(
                        signal,
                        ev.facts,
                        ev.view,
                        tradebook.balance,
                    )
                    if candidate is not None:
                        tradebook.submit_order(
                            candidate,
                            signal,
                            name,
                            ev.view.current.timestamp,
                            instrument=ev.instrument.canonical,
                        )
                        self._position = ev.instrument
                        self._pending_ts = ev.view.current.timestamp
                        return

    @staticmethod
    def _collect_evidence(facts: dict[FactKey, Fact]) -> tuple[EvidenceEntry, ...]:
        collector = EvidenceCollector()
        for fact in facts.values():
            for entry in fact.evidence:
                collector.add(
                    text=entry.text,
                    level=entry.level,
                    source=entry.source,
                    annotation_hint=entry.annotation_hint,
                )
        return collector.entries()
