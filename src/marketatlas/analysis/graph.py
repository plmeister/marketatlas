from __future__ import annotations

from collections import defaultdict
from typing import Any

from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact

from .base import Analyzer

FactKey = tuple[type[Fact], str]


class CyclicDependencyError(Exception):
    def __init__(self, cycle: list[FactKey]) -> None:
        names = " → ".join(f"{t.__name__}({k})" for t, k in cycle)
        super().__init__(f"Cyclic dependency detected: {names}")
        self.cycle = cycle


class UnsatisfiedDependencyError(Exception):
    def __init__(self, analyzer: Analyzer, missing: FactKey) -> None:
        fact_type, key = missing
        super().__init__(
            f"{type(analyzer).__name__} requires {fact_type.__name__}({key}) "
            f"but no analyzer produces it"
        )
        self.analyzer = analyzer
        self.missing = missing


class AnalysisGraph:
    def __init__(self, analyzers: list[Analyzer]) -> None:
        self._analyzers = list(analyzers)
        self._execution_order = self._topo_sort()

    def _topo_sort(self) -> list[Analyzer]:
        produces_map: dict[FactKey, Analyzer] = {}
        for analyzer in self._analyzers:
            for fact_type, key in analyzer.produces():
                fk = (fact_type, key)
                if fk in produces_map:
                    raise CyclicDependencyError([fk])
                produces_map[fk] = analyzer

        for analyzer in self._analyzers:
            for req in analyzer.requires():
                if req not in produces_map:
                    raise UnsatisfiedDependencyError(analyzer, req)

        in_degree: dict[int, int] = {i: 0 for i in range(len(self._analyzers))}
        adjacency: dict[int, list[int]] = defaultdict(list)

        analyzer_index = {id(a): i for i, a in enumerate(self._analyzers)}

        for i, analyzer in enumerate(self._analyzers):
            for req in analyzer.requires():
                producer = produces_map[req]
                j = analyzer_index[id(producer)]
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
            cycle_nodes = [self._analyzers[i] for i in remaining]
            all_fact_keys: list[FactKey] = []
            for a in cycle_nodes:
                all_fact_keys.extend(a.produces())
            raise CyclicDependencyError(all_fact_keys[:1])

        return [self._analyzers[i] for i in sorted_indices]

    def execution_order(self) -> list[Analyzer]:
        return list(self._execution_order)

    def run(self, view: MarketView) -> dict[FactKey, Fact]:
        facts: dict[FactKey, Fact] = {}
        for analyzer in self._execution_order:
            result = analyzer.analyze(view, facts)
            produces = analyzer.produces()
            for i, fact in enumerate(result.facts):
                facts[produces[i]] = fact
        return facts


class AnalyzerRegistry:
    def __init__(self) -> None:
        self._entries: list[tuple[type[Analyzer], dict[str, Any]]] = []

    def register(self, cls: type[Analyzer], **kwargs: Any) -> None:
        self._entries.append((cls, kwargs))

    def build(self) -> AnalysisGraph:
        analyzers: list[Analyzer] = []
        for cls, kwargs in self._entries:
            analyzers.append(cls(**kwargs))
        return AnalysisGraph(analyzers)

    def resolve(self, needed: set[FactKey]) -> AnalysisGraph:
        # Instantiate all registered analyzers to discover what they produce
        candidates: list[Analyzer] = []
        for cls, kwargs in self._entries:
            candidates.append(cls(**kwargs))

        # Collect what candidates produce
        produces_map: dict[FactKey, Analyzer] = {}
        for a in candidates:
            for fk in a.produces():
                produces_map[fk] = a

        # Find which candidates are needed (transitively)
        required: set[FactKey] = set(needed)
        resolved: set[int] = set()  # by id

        while True:
            new_required: set[FactKey] = set()
            for fk in required:
                if fk in produces_map and id(produces_map[fk]) not in resolved:
                    analyzer = produces_map[fk]
                    resolved.add(id(analyzer))
                    for dep_fk in analyzer.requires():
                        if dep_fk not in produces_map:
                            raise UnsatisfiedDependencyError(analyzer, dep_fk)
                        new_required.add(dep_fk)
            if new_required - required == set():
                break
            required |= new_required

        ordered = [a for a in candidates if id(a) in resolved]
        return AnalysisGraph(ordered)
