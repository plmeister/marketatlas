from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.data.store import MarketStore
from marketatlas.data.view import MarketView
from marketatlas.evidence.collector import EvidenceCollector
from marketatlas.evidence.model import EvidenceEntry
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.frames.store import FrameStore
from marketatlas.strategy.risk import RiskEngine
from marketatlas.strategy.tradebook import TradeBook

if TYPE_CHECKING:
    from marketatlas.facts.base import Fact
    from marketatlas.strategy.signals import TradeSignal


@dataclass(frozen=True)
class BacktestResult:
    """Complete backtest output, safe to pickle for later inspection."""

    store: MarketStore
    frames: FrameStore
    tradebook: TradeBook
    window_size: int
    max_hold_days: int


@runtime_checkable
class BundleProtocol(Protocol):
    @property
    def graph(self) -> AnalysisGraph: ...
    @property
    def tradebook(self) -> TradeBook: ...
    @property
    def strategies(self) -> dict[str, Any]: ...
    def evaluate_all(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> list[tuple[str, TradeSignal]]: ...
    def evaluate_all_with_rejections(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> tuple[list[tuple[str, TradeSignal]], list[tuple[str, TradeSignal]]]: ...
    def get_risk_engine(self, strategy_name: str) -> RiskEngine: ...


class Backtester:
    def __init__(
        self,
        store: MarketStore,
        bundle: BundleProtocol,
        window_size: int = 100,
        max_hold_days: int = 10,
    ) -> None:
        self._store = store
        self._bundle = bundle
        self._window_size = window_size
        self._max_hold_days = max_hold_days

    @property
    def frame_count(self) -> int:
        return max(0, len(self._store) - self._window_size)

    def run(self) -> BacktestResult:
        return self.run_with_progress(None)

    def run_with_progress(
        self,
        callback: Callable[[int, int], None] | None = None,
    ) -> BacktestResult:
        frame_store = FrameStore()
        tradebook = self._bundle.tradebook
        symbol = str(self._store.symbol)
        total = self.frame_count
        for i, cursor in enumerate(range(self._window_size, len(self._store))):
            view = MarketView(self._store, cursor, self._window_size)
            facts, loose_evidence = self._bundle.graph.run_with_evidence(view)
            evidence = self._collect_evidence(facts) + loose_evidence

            emitted, signal_rejections = self._bundle.evaluate_all_with_rejections(
                view, facts
            )
            signals = tuple(signal for _, signal in emitted)
            rejection_entries = list(
                e for _, sig in signal_rejections for e in sig.rejections
            )

            tradebook.fill_order(view.current, symbol)
            tradebook.resolve_at_cursor(view.current, self._max_hold_days, symbol)

            risk_evidence: tuple[EvidenceEntry, ...] = ()
            if tradebook.has_no_open_trade and not tradebook.has_pending_order:
                for name, signal in emitted:
                    risk_engine = self._bundle.get_risk_engine(name)
                    candidate, evidence = risk_engine.evaluate(
                        signal,
                        facts,
                        view,
                        tradebook.balance,
                    )
                    if candidate is not None:
                        risk_evidence = evidence
                        tradebook.submit_order(
                            candidate,
                            signal,
                            name,
                            view.current.timestamp,
                            instrument=symbol,
                        )
                        break
                    # Signal passed the signal layer but the risk engine
                    # filtered it out (no valid RR, S/R crossing, stop too
                    # wide, missing ATR/SR, ...). Surface the reason so users
                    # can see why the signal did not become a trade.
                    rejection_entries.extend(evidence)

            frame = AnalysisFrame(
                timestamp=view.current.timestamp,
                candle=view.current,
                facts=dict(facts),
                evidence=evidence,
                signals=signals,
                risk_evidence=risk_evidence,
                signal_rejections=tuple(rejection_entries),
            )
            frame_store.append(frame)

            if callback is not None:
                callback(i + 1, total)

        if not tradebook.has_no_open_trade:
            last_cursor = self._window_size + len(frame_store) - 1
            tradebook.close_trade(
                self._store[last_cursor].close,
                self._store[last_cursor].timestamp,
                symbol,
            )

        return BacktestResult(
            store=self._store,
            frames=frame_store,
            tradebook=tradebook,
            window_size=self._window_size,
            max_hold_days=self._max_hold_days,
        )

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
