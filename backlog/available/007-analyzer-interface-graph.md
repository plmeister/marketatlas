# Analyzer Interface and Dependency Graph

**Epic:** mvp

## Problem

Analyzers need a common interface. The system must auto-resolve execution order based on declared dependencies — no hardcoded pipelines.

## Goal

`Analyzer` base class with `requires()` / `produces()` declarations. `AnalysisGraph` builds execution order from declarations.

## Design

### 1. Analyzer Base

File: `src/marketatlas/analysis/base.py`

```python
from abc import ABC, abstractmethod

class Analyzer(ABC):
    @abstractmethod
    def requires(self) -> tuple[type[Fact], ...]: ...

    @abstractmethod
    def produces(self) -> tuple[type[Fact], ...]: ...

    @abstractmethod
    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult: ...
```

### 2. AnalysisResult

File: `src/marketatlas/analysis/result.py`

```python
@dataclass(frozen=True)
class AnalysisResult:
    facts: tuple[Fact, ...]
    evidence: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()
```

### 3. AnalysisGraph

File: `src/marketatlas/analysis/graph.py`

```python
class AnalysisGraph:
    def __init__(self, analyzers: list[Analyzer]): ...

    def execution_order(self) -> list[Analyzer]: ...

    def run(self, view: MarketView) -> dict[type[Fact], Fact]: ...
```

Graph builder:
- Collect all `produces()` and `requires()` declarations
- Topological sort — analyzers with no unsatisfied deps first
- Raise `CyclicDependencyError` if cycle detected
- Raise `UnsatisfiedDependencyError` if required fact not producible

### 4. Tests

- Two analyzers: A produces X, B requires X → execution order [A, B]
- Circular dependency raises error
- Missing dependency raises error
- `graph.run(view)` returns dict of all produced facts

## Evidence

- `AnalysisGraph([ema_analyzer, trend_analyzer]).execution_order()` returns correct order
- `graph.run(view)` produces all expected fact types
