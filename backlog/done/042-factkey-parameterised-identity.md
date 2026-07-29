# 042: FactKey and Parameterised Fact Identity

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Introduce `FactKey` as a typed, parameterised identity for facts. Ensure EMA(20) and EMA(50) are distinct identities, not both just "ema". Update graph deduplication to use these identities.

## Acceptance Criteria

- [ ] `FactKey` dataclass: `name: str`, `params: dict[str, Any]` (e.g. `FactKey("ema", {"period": 20})`)
- [ ] `FactKey.__str__()` produces human-readable key (e.g. `"ema_20"`)
- [ ] `FactKey.__hash__()` and `__eq__()` based on name + params
- [ ] Analyzers declare `produces()` as `tuple[FactKey, ...]` instead of string keys
- [ ] Graph deduplication uses `FactKey` equality — two EMAAnalyzer(20) instances dedup to one
- [ ] Existing string-keyed API backward compat (wrap in adapter or migrate callers)
- [ ] All existing tests pass without modification

## Design Sketch

```python
@dataclass(frozen=True)
class FactKey:
    name: str
    params: frozenset[tuple[str, Any]] = frozenset()

    def __str__(self) -> str:
        parts = [self.name]
        for k, v in sorted(self.params):
            parts.append(f"{k}_{v}")
        return "_".join(parts)

# Analyser declares:
class EMAAnalyzer(Analyzer):
    @classmethod
    def produces(cls) -> tuple[FactKey, ...]:
        return (FactKey("ema", {"period": cls.period}),)
```

## Related

- Backlog 036: AST model
- `src/marketatlas/analysis/graph.py` — dedup logic
- Backlog 040: Compiler adapter
