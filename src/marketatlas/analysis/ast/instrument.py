from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from marketatlas.analysis.ast.models import Analysis
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.data.instrument import Instrument
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Timeframe
from marketatlas.frames.store import FrameStore
from marketatlas.strategy.config import StrategyConfig
from marketatlas.strategy.tradebook import TradeBook

if TYPE_CHECKING:
    from marketatlas.analysis.ast.requirements import DataRequirement


@dataclass(frozen=True)
class InstrumentGraph:
    """A materialized per-instrument analysis graph (backlog 063).

    ``instrument`` carries the identity the results are namespaced under;
    ``graph`` is a fresh, isolated ``AnalysisGraph`` — the runtime never
    reuses analyzer instances across instruments, so facts can never leak
    between per-instrument runs.
    """

    instrument: Instrument
    graph: AnalysisGraph

    @property
    def canonical(self) -> str:
        return self.instrument.canonical


class TemplateGraph:
    """Instrument-neutral compiled template (backlog 063).

    The DSL/AST describes one implicit instrument; ``TemplateGraph`` is the
    recipe between the concrete AST and execution. It owns the concrete
    ``Analysis`` plus its ``StrategyConfig`` (the compile-time recipe) and can
    rebuild a fresh, isolated ``AnalysisGraph`` per instrument on demand.
    Compilation happens once (``Pipeline.compile_template``); instantiation is
    cheap and repeatable — it only re-runs analyzer construction, never the
    compiler pipeline.

    The reference ``graph`` (``self.graph``) is the instrument-neutral
    structure: identical for every instrument, but never the object handed to
    a run. ``instantiate``/``instantiate_all`` materialize per-instrument
    copies so per-instrument runs share no analyzer state.
    """

    def __init__(self, analysis: Analysis, config: StrategyConfig) -> None:
        self._analysis = analysis
        self._config = config
        self._graph = self._build_graph()

    @property
    def analysis(self) -> Analysis:
        return self._analysis

    @property
    def config(self) -> StrategyConfig:
        return self._config

    @property
    def graph(self) -> AnalysisGraph:
        """The instrument-neutral reference graph (read-only structure)."""
        return self._graph

    def instantiate(self, instrument: Instrument) -> InstrumentGraph:
        """Materialize a fresh, isolated graph for ``instrument``."""
        return InstrumentGraph(instrument=instrument, graph=self._build_graph())

    def instantiate_all(self, instruments: Sequence[Instrument]) -> tuple[InstrumentGraph, ...]:
        """Materialize one isolated graph per instrument, in order.

        The instrument list is a runtime concern — the DSL never names an
        instrument. An empty list raises: there is nothing to instantiate.
        """
        if not instruments:
            raise ValueError("At least one instrument is required to instantiate a template")
        return tuple(self.instantiate(i) for i in instruments)

    def required_timeframes(self) -> tuple[Timeframe, ...]:
        """Effective timeframes this template needs (backlog 065).

        Derived from the compiled ``StrategyConfig.timeframes``, which is the
        declared ``Analysis.timeframes`` or the strategy base default
        (``("1d",)``) when the template declares none — the exact set the
        runtime will run against. Deterministic, declaration order.
        """
        from marketatlas.analysis.ast.requirements import _config_timeframes

        return _config_timeframes(self._config)

    def required_data(
        self,
        instruments: Sequence[Instrument],
        start: datetime,
        end: datetime,
    ) -> tuple[DataRequirement, ...]:
        """The ``(instrument, timeframe)`` data needs for a run (backlog 065).

        Cartesian product over the template's effective timeframes and the
        runtime instrument list, deduplicated by instrument identity and
        deterministically ordered. The empty instrument list raises (matching
        ``instantiate_all``); date range is carried so callers can check store
        coverage before fetching.
        """
        from marketatlas.analysis.ast.requirements import _requirements_for

        return _requirements_for(self._config, instruments, start, end)

    def _build_graph(self) -> AnalysisGraph:
        from marketatlas.strategy.loader import build_analyzers

        return AnalysisGraph(build_analyzers(self._config))


@dataclass(frozen=True)
class InstrumentBacktestResult:
    """Results of one instrument's backtest, namespaced by identity."""

    instrument: Instrument
    frames: FrameStore
    tradebook: TradeBook

    @property
    def canonical(self) -> str:
        return self.instrument.canonical


def backtest_template(
    template: TemplateGraph,
    stores: Sequence[tuple[Instrument, MarketStore]],
    *,
    initial_balance: float = 1000.0,
    window_size: int = 100,
    max_hold_days: int = 10,
) -> tuple[InstrumentBacktestResult, ...]:
    """Run one template across many instruments (backlog 063).

    Each ``(instrument, store)`` pair runs an isolated backtest built from the
    shared template recipe — per-instrument ``Strategy``/``StrategyBundle``
    instances own fresh analyzers, frames, and tradebooks, so results never
    cross-contaminate. The instrument list is supplied at runtime; an empty
    list raises.
    """
    if not stores:
        raise ValueError("At least one (instrument, store) pair is required")
    from marketatlas.backtesting.backtester import Backtester
    from marketatlas.strategy.bundle import StrategyBundle
    from marketatlas.strategy.strategy import Strategy

    results: list[InstrumentBacktestResult] = []
    for instrument, store in stores:
        strategy = Strategy(template.analysis.name, template.config)
        bundle = StrategyBundle([strategy], initial_balance=initial_balance)
        bt = Backtester(store, bundle, window_size=window_size, max_hold_days=max_hold_days)
        frames, tradebook = bt.run()
        results.append(
            InstrumentBacktestResult(instrument=instrument, frames=frames, tradebook=tradebook)
        )
    return tuple(results)
