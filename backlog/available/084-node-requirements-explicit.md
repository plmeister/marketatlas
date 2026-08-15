# 084: Node requirements declared in DSL — no auto-located fact keys

**Status:** pending
**Epic:** ast
**Priority:** high
**Depends on:** 058, 062, 083

## Description

Analyzers, signals, and risk nodes all resolve facts by **constructor key
defaults** (`*_key: str = "…"`) that silently auto-locate a fact by name:

- Analyzers — `TrendAnalyzer(fast_key="ema_20", slow_key="ema_50", atr_key="atr_14")`
  (`analyzers/trend.py:16-18`), `sr(swing_key="swing", atr_series_key="atr_14_series")`
  (`analyzers/sr.py:19-20`), `swing_structure(swing_key="swing")`
  (`analyzers/swing_structure.py:16`)
- Signals — `PullbackSignal(pullback_key="pullback_pattern", trend_key="trend", atr_key="atr_14")`
  (`analysis/signals/pullback_signal.py:32-34`); it ignores the compiled
  `SignalConfig.requires` at runtime and name-matches by its own defaults
- Risk — covered by backlog 083

The DSL can reference facts explicitly, but nothing enforces completeness:
`trend { ema_20: ema20, ema_50: ema50 }` omits `atr_14` yet compiles and the
analyzer picks up whatever fact is named `atr_14` (any timeframe). Same
fragility class as 083 for the rest of the graph.

**Principle:** no node locates its own requirements. Every fact a node
consumes is declared explicitly in the DSL; omitting a required input is a
compile error.

## Design

1. **Provider contracts cover every node category.** Extend `ProviderContract`
   (`registry.py:20-29`) so signal and risk providers declare their input fact
   names, not just analyzers. Today `_derive_contract` reads
   `instance.requires()` and only analyzer classes have it
   (`registry.py:161-181`); give `Signal` subclasses and `RiskEngine` an
   equivalent `requires()`/input declaration and derive contracts uniformly.
2. **Compiler enforces completeness.** In `_compile_strategy`, for each
   definition, every contract-declared input fact must be supplied as a
   `ReferenceExpression`. Missing → `CompilationError` naming the definition
   and the missing fact (e.g. `definition 'signal' is missing required fact
   input 'trend'`).
3. **Compiler injects explicit keys.** References compile to fact-key strings
   in the node's params (with the `@timeframe` suffix when the reference
   crosses timeframes — existing 062 mechanism), and nodes consume only those
   injected keys:
   - Analyzers: existing `params["bindings"]` path — unchanged
   - Signals: `PullbackSignal` constructor param names align with the DSL
     reference names (`pullback_pattern`, `trend`, `atr_14`) so
     `PullbackSignal(**rules)` receives explicit keys; the compiled
     `SignalConfig.requires`/key params are what evaluate() resolves
   - Risk: `bindings` per backlog 083
4. **Trend ATR becomes a declared input.** `TrendAnalyzer.requires()` gains
   `atr_14` and it is added to its contract — the strength fallback to price
   when ATR is absent (currently optional `facts.get`, `trend.py:55`) is
   replaced by a hard dependency so the DSL must declare it. swing.dsl trend
   node gains `atr_14: atr_14`.
5. **Defaults stay only for programmatic/YAML construction**, where the
   constructor or config is itself the explicit declaration. `resolve_fact_key`
   name-fallback remains reachable only from those legacy paths — a
   DSL-compiled strategy never has an undeclared key.
6. **swing.dsl becomes fully explicit**: signal refs (already present),
   risk refs (083), trend `atr_14`, `sr` inputs, `swingstructure` input.

## Acceptance Criteria

- [ ] Analyzer, signal, and risk definitions that omit a contract-declared
      input fail to compile with an error naming the definition and missing
      fact (e.g. `trend { ema_20: ema20, ema_50: ema50 }` without `atr_14`)
- [ ] References on all three node categories are validated via
      `_check_fact_declared` (referenced definition must produce the fact)
- [ ] `PullbackSignal` consumes the injected keys from DSL references; with
      keys injected it never falls back to constructor defaults
- [ ] `TrendAnalyzer.requires()` includes `atr_14`; its contract lists it;
      DSL must declare it
- [ ] Cross-timeframe references still compile to `name@tf` keys and resolve
      the intended timeframe fact
- [ ] YAML loader and direct-construction paths behave unchanged (defaults and
      explicit `requires`/key strings still valid there)
- [ ] `strategy/swing.dsl` compiles with every node's inputs declared; golden
      compiler tests assert injected keys for a representative signal +
      analyzer + risk
- [ ] New compiler error tests + updated swing.dsl integration tests pass
- [ ] `poetry run lint` green; full pytest suite green

## Related

- `src/marketatlas/analysis/ast/registry.py` — `ProviderContract` (`:20`),
  `_derive_contract` (`:161`)
- `src/marketatlas/analysis/ast/pipeline.py` — `_compile_strategy` (`:671`),
  `_resolve_reference` (`:793`), `_check_fact_declared` (`:867`)
- `src/marketatlas/analysis/signals/pullback_signal.py` — key defaults (`:32`)
- `src/marketatlas/analysis/analyzers/trend.py`, `sr.py`,
  `swing_structure.py` — `*_key` defaults
- `src/marketatlas/strategy/risk.py` — `RiskEngine` keys (backlog 083)
- `src/marketatlas/strategy/config.py` — `SignalConfig.requires` (`:17`)
- `strategy/swing.dsl` — must become fully explicit
