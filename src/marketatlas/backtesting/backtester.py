from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from marketatlas.analysis.graph import AnalysisGraph, FactKey
from marketatlas.data.store import MarketStore
from marketatlas.data.view import MarketView
from marketatlas.evidence.collector import EvidenceCollector
from marketatlas.evidence.model import EvidenceEntry
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.frames.store import FrameStore

if TYPE_CHECKING:
    from marketatlas.facts.base import Fact


class Backtester:
    def __init__(
        self,
        store: MarketStore,
        graph: AnalysisGraph,
        window_size: int = 100,
    ) -> None:
        self._store = store
        self._graph = graph
        self._window_size = window_size

    @property
    def frame_count(self) -> int:
        return max(0, len(self._store) - self._window_size)

    def run(self) -> FrameStore:
        return self.run_with_progress(None)

    def run_with_progress(
        self, callback: Callable[[int, int], None] | None = None,
    ) -> FrameStore:
        frame_store = FrameStore()
        total = self.frame_count
        for i, cursor in enumerate(range(self._window_size, len(self._store))):
            view = MarketView(self._store, cursor, self._window_size)
            facts = self._graph.run(view)
            evidence = self._collect_evidence(facts)
            frame = AnalysisFrame(
                timestamp=view.current.timestamp,
                candle=view.current,
                facts=dict(facts),
                evidence=evidence,
            )
            frame_store.append(frame)
            if callback is not None:
                callback(i + 1, total)
        return frame_store

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
