from collections import defaultdict

from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact

from .base import Analyzer


class CyclicDependencyError(Exception):
    def __init__(self, cycle: list[type[Fact]]) -> None:
        names = " → ".join(t.__name__ for t in cycle)
        super().__init__(f"Cyclic dependency detected: {names}")
        self.cycle = cycle


class UnsatisfiedDependencyError(Exception):
    def __init__(self, analyzer: Analyzer, missing: type[Fact]) -> None:
        super().__init__(
            f"{type(analyzer).__name__} requires {missing.__name__} "
            f"but no analyzer produces it"
        )
        self.analyzer = analyzer
        self.missing = missing


class AnalysisGraph:
    def __init__(self, analyzers: list[Analyzer]) -> None:
        self._analyzers = list(analyzers)
        self._execution_order = self._topo_sort()

    def _topo_sort(self) -> list[Analyzer]:
        produces_map: dict[type[Fact], Analyzer] = {}
        for analyzer in self._analyzers:
            for fact_type in analyzer.produces():
                if fact_type in produces_map:
                    raise CyclicDependencyError([fact_type])
                produces_map[fact_type] = analyzer

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
            all_fact_types: list[type[Fact]] = []
            for a in cycle_nodes:
                all_fact_types.extend(a.produces())
            raise CyclicDependencyError(all_fact_types[:1])

        return [self._analyzers[i] for i in sorted_indices]

    def execution_order(self) -> list[Analyzer]:
        return list(self._execution_order)

    def run(self, view: MarketView) -> dict[type[Fact], Fact]:
        facts: dict[type[Fact], Fact] = {}
        for analyzer in self._execution_order:
            result = analyzer.analyze(view, facts)
            for fact in result.facts:
                facts[type(fact)] = fact
        return facts
