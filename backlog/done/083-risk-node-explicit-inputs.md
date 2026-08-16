# 083: Risk nodes consume facts via explicit DSL references

**Status:** pending
**Epic:** ast
**Priority:** high
**Depends on:** 021, 043, 045, 052, 061, 062

## Description

`manage_risk` finds its inputs by **name convention** at runtime, unlike
analyzer and signal nodes which take explicit references. The compiler treats
risk as an opaque consumer — references contribute nothing
(`pipeline.py:767`, `_resolve_reference` returns empty for risk at
`pipeline.py:864`). `RiskEngine` then matches facts by default key strings
(`atr_key="atr_14"`, `sr_key="sr"`, `swing_key="swing"`,
`strategy/risk.py:29-31`) via `resolve_fact_key` name matching.

This is fragile: rename a definition (e.g. `sr` → `sr_weekly`) and the risk
node silently rejects at runtime with "no SR fact available" — nothing fails
at compile time. Worse, swing.dsl has no fact literally named `swing` (only
`swing1w`/`swing1d`), so the swing anchor is never found and every stop falls
back to `entry ∓ 2·ATR` (`risk.py:242-245`) — the swing-anchored stop design
is dead in the flagship strategy.

**Goal:** risk inputs are explicitly declared in the DSL as fact references,
compiled to dependency edges, validated at compile time, and consumed by
`RiskEngine` at runtime. Name-matching remains only as a legacy fallback.

## Design

DSL becomes:

```
risk := manage_risk {
  atr_14: atr_14,   // reference params name the produced fact (existing convention)
  sr: sr,
  swing: swing1d,
  risk_pct: 1.0,
  min_rr: 1.0,
  max_rr: 4.0,
  max_stop_atr: 7.0,
}
```

- **Compiler (`pipeline.py`)**: in `_resolve_reference`, give the risk
  category the same treatment as analyzers — call `_check_fact_declared`
  (reference param must be a fact the target produces; catches `atr: atr_14`
  role-name mismatches with a clear `CompilationError`) and return a
  `binding` carrying the source-timeframe suffix for cross-timeframe
  references (`swing: swing1w` → `swing@1w`). Collect risk bindings into
  `params["bindings"]` exactly like the analyzer path (`pipeline.py:717-718`).
  Timeframe and spanning references stay invalid on risk nodes.
- **`RiskConfig`**: unchanged shape — bindings ride in `params["bindings"]`,
  so `Strategy._build_risk` (`strategy/strategy.py:64-66`) already forwards
  them with no change.
- **`RiskEngine`**: add `bindings: dict[str, str] | None = None` to
  `__init__`. In `evaluate`, resolve each consumer by its default key with a
  binding override — `resolve_fact_key(facts, self._bindings.get(key, key))`
  for atr/sr/swing. With no bindings the legacy key defaults apply unchanged
  (YAML loader path and direct-construction tests keep working).
- **`strategy/swing.dsl`**: add the explicit references above.
  **Behavior change to flag:** wiring `swing: swing1d` activates the
  swing-anchored stop (latest swing low/high + 0.2·ATR buffer) instead of the
  2·ATR fallback — backtest numbers will change. This is the intended fix,
  not a regression.
- **Compiler golden tests** (`tests/test_compiler_golden.py`): assert the
  emitted `RiskConfig` carries `bindings`.

## Acceptance Criteria

- [ ] `manage_risk { sr: sr, atr_14: atr_14, swing: swing1d, … }` compiles to
      a `RiskConfig` whose `params["bindings"]` carry the fact keys
- [ ] Risk node with a reference that the target does not produce fails at
      compile time (e.g. `manage_risk { atr: atr_14 }` or `manage_risk { sr: ema20 }`
      → `CompilationError` naming the produced facts)
- [ ] Cross-timeframe reference (`swing: swing1w`) compiles to a `swing@1w`
      binding and `RiskEngine` resolves the weekly swing fact
- [ ] `RiskEngine` without `bindings` keeps legacy `atr_key`/`sr_key`/`swing_key`
      behavior (all existing direct-construction tests pass unchanged)
- [ ] `RiskEngine` with `bindings` uses the bound fact even when the legacy
      default key differs
- [ ] `strategy/swing.dsl` risk node declares all three inputs explicitly;
      the swing-anchored stop is exercised (no more unconditional 2·ATR fallback
      when a swing fact is available)
- [ ] Unknown reference on a risk node still raises `CompilationError`
      (existing behaviour retained)
- [ ] `poetry run lint` green; full pytest suite green

## Related

- `src/marketatlas/analysis/ast/pipeline.py` — `_resolve_reference`
  (`:793`), risk branch (`:732-733`, `:864`), `_check_fact_declared` (`:867`)
- `src/marketatlas/strategy/risk.py` — `RiskEngine` key defaults (`:29-31`),
  `evaluate` resolution (`:61-76`), `_find_stop_anchor` 2·ATR fallback (`:242`)
- `src/marketatlas/strategy/config.py` — `RiskConfig` (`:21`)
- `src/marketatlas/strategy/strategy.py` — `_build_risk` (`:64`)
- `strategy/swing.dsl` — risk node to update
- **Related finding (not in scope):** `PullbackSignal` also resolves by
  hardcoded key defaults (`analysis/signals/pullback_signal.py:32-34`) and
  ignores the compiled `SignalConfig.requires` — same name-matching pattern,
  smaller blast radius since DSL references already exist. Candidate for a
  follow-up backlog.
