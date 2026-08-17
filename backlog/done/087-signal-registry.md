# 087: Decouple signal registration from Strategy class

**Status:** pending
**Epic:** strategy
**Priority:** medium
**Depends on:** none

## Description

`strategy/strategy.py:51` hardcodes the signal import:

```python
from marketatlas.analysis.signals.pullback_signal import PullbackSignal
```

Adding a new signal type requires editing this file. The project already has
`analysis/ast/registry.py` for DSL type discovery — signals should follow the
same pattern.

Use a registry so signals are discovered by name, not imported by
`Strategy._build_signals()`.

## Design

1. **Signal registry module**: `analysis/signals/registry.py` — a dict mapping
   signal class names to their classes. Registration is explicit:

   ```python
   from marketatlas.analysis.signals.pullback_signal import PullbackSignal
   SIGNAL_TYPES: dict[str, type[Signal]] = {"PullbackSignal": PullbackSignal}
   ```

2. **Strategy._build_signals()** looks up `SIGNAL_TYPES[sc.type]` instead of
   the hardcoded dict. Raises `ValueError` for unknown types (unchanged).

3. **Adding a new signal**: create the file in `analysis/signals/`, add one
   import line to `analysis/signals/registry.py`. No edits to
   `strategy/strategy.py`.

4. **DSL compiler** (`analysis/ast/registry.py`) should also register signal
   types there (it already validates signal types at compile time via
   `ProviderRegistry`). Keep both registries in sync — or derive one from
   the other.

## Acceptance Criteria

- [ ] `strategy/strategy.py` has no signal class imports
- [ ] `analysis/signals/registry.py` contains `SIGNAL_TYPES` dict
- [ ] `Strategy._build_signals()` uses registry lookup
- [ ] Adding a new signal requires only: new file + one registry line
- [ ] `pytest tests/test_signal_system.py tests/test_strategy_bundle.py tests/test_pullback_confirmed_entry.py` pass
- [ ] `ruff check` clean

## Related

- `src/marketatlas/strategy/strategy.py:50-62` — hardcoded signal map
- `src/marketatlas/analysis/signals/pullback_signal.py` — only signal type
- `src/marketatlas/analysis/ast/registry.py` — existing registry pattern
