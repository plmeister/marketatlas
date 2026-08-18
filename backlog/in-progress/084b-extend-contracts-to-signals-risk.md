# 084b: Extend ProviderContract to signals and risk

**Status:** pending
**Epic:** ast
**Priority:** high
**Depends on:** 084a

## Description

`_derive_contract` (`registry.py:161`) reads `requires()`/`produces()` from classes but only analyzer classes have them. After 084a, signals and risk also have `requires()`. But `create_default_registry` (`registry.py:203`) registers signals and risk without calling `register_contract` — their contracts stay empty.

**Goal:** Register contracts for signal and risk providers so the compiler can validate completeness (084c).

## Design

1. In `create_default_registry`, after registering `generate_signal` and `manage_risk`, call `register_contract` with the derived contract
2. `_derive_contract` already handles the `requires()`/`produces()` pattern — just needs to be called for signal/risk providers
3. No changes to `_derive_contract` itself

## Files

- `analysis/ast/registry.py` — `create_default_registry`: add `register_contract` calls for signal and risk

## Acceptance Criteria

- [ ] `registry.contract("generate_signal")` returns a contract with `inputs=("pullback_pattern", "trend", "atr_14")`
- [ ] `registry.contract("manage_risk")` returns a contract with `inputs=("atr_14", "sr", "swing")`
- [ ] Existing tests pass
- [ ] `poetry run pytest -m tier1` green

## Related

- `analysis/ast/registry.py:161` — `_derive_contract`
- `analysis/ast/registry.py:225-228` — signal/risk registration (no contract)
