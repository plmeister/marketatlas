from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from marketatlas.analysis.graph import AnalysisGraph, FactKey
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


@runtime_checkable
class BundleProtocol(Protocol):
    @property
    def graph(self) -> AnalysisGraph: ...
    @property
    def tradebook(self) -> TradeBook: ...
    def evaluate_all(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> list[tuple[str, TradeSignal]]: ...
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

    def run(self) -> tuple[FrameStore, TradeBook]:
        return self.run_with_progress(None)

    def run_with_progress(
        self, callback: Callable[[int, int], None] | None = None,
    ) -> tuple[FrameStore, TradeBook]:
        frame_store = FrameStore()
        tradebook = self._bundle.tradebook
        total = self.frame_count
        for i, cursor in enumerate(range(self._window_size, len(self._store))):
            view = MarketView(self._store, cursor, self._window_size)
            facts = self._bundle.graph.run(view)
            evidence = self._collect_evidence(facts)
            frame = AnalysisFrame(
                timestamp=view.current.timestamp,
                candle=view.current,
                facts=dict(facts),
                evidence=evidence,
            )
            frame_store.append(frame)

            tradebook.fill_order(view.current.open, view.current.timestamp)
            tradebook.resolve_at_cursor(view.current, self._max_hold_days)

            if tradebook.has_no_open_trade and not tradebook.has_pending_order:
                for name, signal in self._bundle.evaluate_all(view, facts):
                    risk_engine = self._bundle.get_risk_engine(name)
                    candidate, _ = risk_engine.evaluate(
                        signal, facts, view, tradebook.balance,
                    )
                    if candidate is not None:
                        tradebook.submit_order(
                            candidate, signal, name, view.current.timestamp,
                        )
                        break

            if callback is not None:
                callback(i + 1, total)

        if not tradebook.has_no_open_trade:
            last_cursor = self._window_size + len(frame_store) - 1
            tradebook.close_trade(
                self._store[last_cursor].close,
                self._store[last_cursor].timestamp,
            )

        return frame_store, tradebook

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
