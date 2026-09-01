from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from marketatlas.analysis.ast.models import Analysis
from marketatlas.analysis.ast.registry import ProviderRegistry, create_default_registry
from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.graph import AnalysisGraph, CyclicDependencyError
from marketatlas.data.instrument import Instrument
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact
from marketatlas.frames.store import FrameStore
from marketatlas.strategy.config import AnalyzerConfig, StrategyConfig
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

    Group-scoped definitions (backlog 064) are *not* part of the
    per-instrument recipe: ``config`` holds only per-instrument nodes and
    ``group_config`` only group nodes. Group nodes cannot be instantiated per
    instrument — their spanning inputs depend on the runtime member list, so
    ``instantiate_group`` materializes the group node graph with member
    bindings at call time.
    """

    def __init__(
        self,
        analysis: Analysis,
        config: StrategyConfig,
        group_config: StrategyConfig | None = None,
        registry: ProviderRegistry | None = None,
    ) -> None:
        self._analysis = analysis
        self._config = config
        self._group_config = group_config
        self._registry = registry
        self._graph = self._build_graph()

    @property
    def analysis(self) -> Analysis:
        return self._analysis

    @property
    def config(self) -> StrategyConfig:
        return self._config

    @property
    def group_config(self) -> StrategyConfig | None:
        """The group-only config; ``None`` when the template has no group nodes."""
        return self._group_config

    @property
    def has_group(self) -> bool:
        return self._group_config is not None and bool(self._group_config.analyzers)

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

    def instantiate_group(self, group: str, members: Sequence[Instrument]) -> GroupGraph:
        """Materialize one group run: N per-instrument graphs + 1 group node graph.

        Group membership is a runtime concern, like the instrument list for
        ``instantiate_all`` (backlog 064). ``members`` orders the member
        graphs; the group node graph is built fresh with member bindings so no
        analyzer state is shared between group runs. An empty member list
        raises, and a template with no group-scoped definitions cannot be
        instantiated as a group.
        """
        if not members:
            raise ValueError("At least one instrument is required to instantiate a group")
        if self._group_config is None or not self._group_config.analyzers:
            raise ValueError(
                f"Template '{self._analysis.name}' has no group-scoped definitions "
                "to instantiate"
            )
        member_graphs = self.instantiate_all(members)
        group_graph = GroupNodeGraph(
            _build_group_analyzers(
                self._group_config,
                [m.canonical for m in members],
                self._registry,
            )
        )
        return GroupGraph(
            group=group,
            members=tuple(members),
            member_graphs=member_graphs,
            group_graph=group_graph,
        )

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

        return AnalysisGraph(build_analyzers(self._config, self._registry))


class GroupNodeGraph:
    """The group node graph: one instance of every group-scoped analyzer.

    Backlog 064: a group node aggregates the outputs of per-instrument sibling
    nodes across the whole group. Its ``requires()`` names one member fact key
    per member, so a plain ``AnalysisGraph`` cannot host it — the member facts
    are external inputs. ``run`` seeds the namespace with member facts
    (namespaced by member canonical) and executes the group analyzers in
    topological order, tolerating those external inputs.
    """

    def __init__(self, analyzers: list[Analyzer]) -> None:
        self._analyzers = list(analyzers)
        self._order = self._topo_sort()

    def _topo_sort(self) -> list[Analyzer]:
        produced_by: dict[FactKey, Analyzer] = {}
        for analyzer in self._analyzers:
            for fk in analyzer.produces():
                if fk in produced_by:
                    raise CyclicDependencyError([fk])
                produced_by[fk] = analyzer

        index = {id(a): i for i, a in enumerate(self._analyzers)}
        in_degree: dict[int, int] = {i: 0 for i in range(len(self._analyzers))}
        adjacency: dict[int, list[int]] = defaultdict(list)

        for i, analyzer in enumerate(self._analyzers):
            for req in analyzer.requires():
                producer = produced_by.get(req)
                if producer is None:
                    # A member-namespaced fact key: supplied externally by the
                    # group run's member namespace, not by a group analyzer.
                    continue
                j = index[id(producer)]
                if i != j:
                    adjacency[j].append(i)
                    in_degree[i] += 1

        queue = [i for i in range(len(self._analyzers)) if in_degree[i] == 0]
        sorted_indices: list[int] = []
        while queue:
            node = queue.pop(0)
            sorted_indices.append(node)
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_indices) != len(self._analyzers):
            remaining = set(range(len(self._analyzers))) - set(sorted_indices)
            all_fact_keys: list[FactKey] = []
            for a in remaining:
                all_fact_keys.extend(self._analyzers[a].produces())
            raise CyclicDependencyError(all_fact_keys[:1])

        return [self._analyzers[i] for i in sorted_indices]

    def execution_order(self) -> list[Analyzer]:
        """The group analyzers in execution order (topological)."""
        return list(self._order)

    def run(
        self,
        view: MarketView,
        member_facts: Sequence[dict[FactKey, Fact]],
        canonicals: Sequence[str],
    ) -> dict[FactKey, Fact]:
        """Execute group analyzers over a namespace seeded with member facts.

        Each member's facts are re-keyed ``{member_canonical}/name@timeframe``
        so per-member facts cannot collide and group analyzers can read any
        member's output by name. The group node is data-free: ``view`` is only
        a source of the aggregate fact's timestamp.
        """
        namespace: dict[FactKey, Fact] = {}
        for canonical, facts in zip(canonicals, member_facts):
            for fk, fact in facts.items():
                namespace[FactKey(f"{canonical}/{fk.name}", timeframe=fk.timeframe)] = fact
        for analyzer in self._order:
            result = analyzer.analyze(view, namespace)
            for fk, fact in zip(analyzer.produces(), result.facts):
                namespace[fk] = fact
        return namespace


@dataclass(frozen=True)
class GroupGraph:
    """A materialized group run (backlog 064).

    ``members`` carries the runtime-supplied group membership; ``member_graphs``
    are the N per-instrument graphs (isolated, never shared) and
    ``group_graph`` the single group node graph wired to consume one fact per
    member from each.
    """

    group: str
    members: tuple[Instrument, ...]
    member_graphs: tuple[InstrumentGraph, ...]
    group_graph: GroupNodeGraph

    @property
    def canonical(self) -> str:
        return self.group

    def run(self, views: Sequence[MarketView]) -> dict[FactKey, Fact]:
        """Run each member's graph, then the group node over the combined facts."""
        if len(views) != len(self.members):
            raise ValueError(
                f"Expected one view per group member ({len(self.members)}), got {len(views)}"
            )
        member_facts = [g.graph.run(v) for g, v in zip(self.member_graphs, views)]
        canonicals = [m.canonical for m in self.members]
        return self.group_graph.run(views[0], member_facts, canonicals)


def _build_group_analyzers(
    config: StrategyConfig,
    members: Sequence[str],
    registry: ProviderRegistry | None = None,
) -> list[Analyzer]:
    """Build group analyzers with the runtime member list injected.

    The group ``StrategyConfig`` is member-agnostic (compile time); each group
    analyzer must know its group membership to name its spanning inputs, so the
    ``members`` parameter is injected here, at instantiation.
    """
    from marketatlas.strategy.loader import build_analyzers

    reg = registry if registry is not None else create_default_registry()
    classes = reg.analyzer_classes()
    analyzer_configs: list[AnalyzerConfig] = []
    for ac in config.analyzers:
        if ac.type not in classes:
            raise ValueError(f"Unknown group analyzer type '{ac.type}'")
        params = dict(ac.params)
        params["members"] = tuple(members)
        analyzer_configs.append(AnalyzerConfig(type=ac.type, params=params, timeframe=ac.timeframe))
    return build_analyzers(
        StrategyConfig(
            name=config.name,
            version=config.version,
            timeframes=config.timeframes,
            analyzers=tuple(analyzer_configs),
            signals=config.signals,
            risk=config.risk,
        ),
        registry=reg,
    )


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
        result = bt.run()
        results.append(
            InstrumentBacktestResult(
                instrument=instrument,
                frames=result.frames,
                tradebook=result.tradebook,
            )
        )
    return tuple(results)
