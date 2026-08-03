# 058: Provider Contract Metadata — Inputs, Outputs, Params

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Full provider contract metadata: inputs (facts consumed), outputs (facts produced), and parameter schema. The DSL core principle states "provider contracts define inputs, outputs, parameter schemas and validation" — everything the compiler needs to infer dependencies and the DSL needs to disambiguate shorthand fields.

Extends backlog 052's parameter schema with the fact-level contract. Today analyzers expose this only via runtime `requires()`/`produces()` (e.g. ema.py:22,25) and the registry (registry.py) stores none of it.

## Scope

- Provider contract: `inputs` (fact keys/types consumed), `outputs` (fact keys produced), param schema (from 052)
- Default registry derives contracts from analyzer `requires()`/`produces()` signatures (with timeframe/FactKey awareness — 045), manual override where opaque
- Used by:
  - DSL shorthand disambiguation (057): field name matching a provider input → dependency
  - validation: binding `input` must be a declared provider input; `output` must be a declared output (extends 052, still not graph deps)
  - construction API (053): validate input/output names at construction

## Non-Goals

- No graph/dependency inference (compiler stage-4 domain)
- No DSL grammar changes (055 owns those)

## Acceptance Criteria

- [ ] Registry exposes `inputs`/`outputs` per provider for all built-in providers (ema, atr, trend, swingstructure, swings, sr, detect_pullback, generate_signal, manage_risk)
- [ ] Contract derives correctly from `requires()`/`produces()` for at least ema, atr, swing, sr, pullback
- [ ] Validation rejects a binding whose `input` is not a declared provider input
- [ ] Validation rejects a binding whose `output` is not a declared provider output
- [ ] DSL shorthand uses the contract (integrated test with 057)
- [ ] Existing cycle/binding validation tests unchanged (additive checks only)
- [ ] Tests: contract derivation, validation additions, integration with shorthand

## Technical Notes

- Provider dataclass change is additive (defaults preserve existing constructors). Prefer registry-held contract keyed by provider name (consistent with 052).
- FactKey needs mapping to stable names for contract lookup — reuse `FactKey` identity semantics (042).

## Related

- Backlog 052 (param schema — prereq), 057 (shorthand), 053 (construction API)
- `src/marketatlas/analysis/analyzers/`, `src/marketatlas/analysis/ast/registry.py`
