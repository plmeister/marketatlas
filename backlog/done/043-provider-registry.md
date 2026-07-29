# 043: Provider Registry

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Registry that maps capabilities to available providers. Multiple implementations can advertise the same capability. Enables strategies to declare "I need EMA(20)" without specifying which analyzer class, leaving provider selection to the registry.

## Acceptance Criteria

- [ ] `ProviderRegistry` class: `register(provider)`, `resolve(capability) -> Provider`, `list_providers()`
- [ ] Register analyzers, signals, risk engines by capability
- [ ] Capability lookup: `registry.resolve("ema", {"period": 20})` returns first matching provider
- [ ] `register` accepts a `Provider` object or decorator syntax
- [ ] Default registry pre-populated with all built-in analyzers/signals
- [ ] Error: unmatched capability → clear error listing available capabilities
- [ ] Error: ambiguous match (multiple providers) → warn, pick first
- [ ] Bindings remain static (no dynamic resolution during execution) — just prove registration model works

## Design Sketch

```python
registry = ProviderRegistry()
registry.register("ema", EMAAnalyzer, default_params={"period": 20})
registry.register("trend", TrendAnalyzer)
registry.register("pullback", FourSwingPullbackDetector)

provider = registry.resolve("ema", {"period": 50})
# Returns EMAAnalyzer matching EMA(50) capability
```

## Related

- Backlog 041: Capability/Provider/Definition
- Backlog 037: Builder API (builder uses registry)
- `src/marketatlas/analysis/graph.py`
