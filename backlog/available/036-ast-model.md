# 036: AST Model — Core Node Types

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Introduce core AST classes representing an analysis definition. Language-independent semantic model. Immutable, declarative only. No execution or graph compilation involved.

## Acceptance Criteria

- [ ] `Analysis` root node: container for the full definition
- [ ] `Definition` node: a named node in the analysis tree (analyzer, signal, risk config, etc.)
- [ ] `Binding` node: wires one definition's output to another's input via `FactKey`
- [ ] `Parameter` node: key-value pair for configuration (period, threshold, etc.)
- [ ] `BaseNode` base class with common fields (`id`, `type`, `metadata`)
- [ ] All nodes frozen/immutable (dataclass or similar)
- [ ] Complete analysis representable in memory via AST
- [ ] No execution, graph, or runtime logic in AST models

## Design Sketch

```python
@dataclass(frozen=True)
class Parameter:
    name: str
    value: Any

@dataclass(frozen=True)
class Binding:
    source: str       # definition name
    output: str       # output key (FactKey string)
    target: str       # target definition name
    input: str        # input parameter name

@dataclass(frozen=True)
class Definition:
    name: str
    type: str            # "analyzer" | "signal" | "risk" | "transformer"
    impl: str            # e.g. "EMAAnalyzer", "PullbackSignal"
    parameters: tuple[Parameter, ...]
    bindings: tuple[Binding, ...]
    metadata: dict[str, str] | None = None

@dataclass(frozen=True)
class Analysis:
    name: str
    version: str
    definitions: tuple[Definition, ...]
    metadata: dict[str, str] | None = None
```

## Related

- Backlog 037: Builder API
- Backlog 038: Validation
- Backlog 039: Serialization
- Backlog 040: Compiler adapter
