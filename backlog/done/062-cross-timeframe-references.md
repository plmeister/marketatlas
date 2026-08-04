# 062: Cross-Timeframe References — Binding Semantics

**Status:** done  
**Epic:** ast  
**Priority:** high

## Description

Give `Binding` real semantics for analyzer→analyzer dependencies across timeframes. Today bindings only drive signal `requires` (`_ast_to_config`, pipeline.py:219); analyzer dependencies are never wired from the AST — they rely on the provider's `requires()`/`produces()` at runtime. To link nodes by reference across timeframes, the compiler must know which definition (and therefore which timeframe) a reference resolves to, and verify the producer satisfies the consumer.

A consumer at `1d` referencing a producer at `1w` is legal and explicit: `trend := Trend { swings: @swings_1w }`. FactKey identity already encodes timeframe (factkey.py:19); runtime wiring via `view.select` (graph.py:87-90, 045).

## Scope

- Reference resolution: each binding reference resolves to a source definition + its declared timeframe (061)
- Compiler wires analyzer dependencies from bindings (not just signals): validate every binding input/output against provider contracts (058) and produce FactKeys at the correct timeframes
- Cross-timeframe references validated explicitly: a reference may cross timeframes only when the binding declares it; ambiguous/unresolvable references → error
- Signal `requires` derivation updated to carry source timeframe

## Non-Goals

- No group/instrument scoping (backlogs 063/064)
- No data-fetch inference (065)

## Acceptance Criteria

- [x] `trend@1d ← swings@1w` style analysis compiles; `AnalysisGraph.run` selects correct views per node
- [x] Single-timeframe analyses (existing 046 snapshots) compile unchanged — bindings additive, not breaking
- [x] Reference to unknown definition → error; reference whose output isn't declared by provider (058) → error
- [x] Cross-TF reference without explicit declaration → error (or auto-declared per 055 decision — document whichever)
- [x] Signal `requires` includes source timeframe
- [x] Tests: cross-TF wiring, resolution errors, contract mismatches, graph run correctness

## Resolution Notes

- **Binding semantics:** a `field: producer` reference on an analyzer resolves to
  the producer's declared timeframe (061) and is injected as an analyzer
  `bindings` override (`name@timeframe` when the source timeframe differs from
  the consumer's, bare `name` otherwise). `Analyzer._make_key` applies the
  override (skipping the instance key so `produces()` stays stable) and parses
  the `@timeframe` suffix into `FactKey`.
- **Output validation:** implemented via `_check_fact_declared` (instantiate the
  target analyzer with its literal params + source timeframe, check
  `produces()`) rather than static 058 contracts — precise for parameterised
  fact names like `ema_50`.
- **Signals:** a signal reference to a non-base-timeframe definition emits a
  `requires` entry `name@source_tf`; base-timeframe/single-TF entries stay bare
  (`("atr_14",)` — existing 046 behavior preserved).
- **Explicit declaration is the rule:** an undeclared cross-timeframe dependency
  (consumer needs a fact only produced on another timeframe, no reference)
  fails at graph construction with `UnsatisfiedDependencyError`. This documents
  the 055 decision as *declarations only*.
- **055/Runtime decision:** parser emits reference expressions; the compiler
  resolves them to definitions + timeframes. No parser change needed.

## Technical Notes

- This is where the DSL `Reference` expression (055) meets the AST `Binding` — decide whether parser emits bindings with explicit source/TF or the compiler infers it from definition lookup.
- Watch `_ast_to_config` (pipeline.py:203): it currently drops analyzer bindings; the compiler-side wiring is the core change.

## Related

- Backlog 061 (node timeframes — prereq), 058 (provider contracts), 055 (Reference expression), 045 (view selection)
- `src/marketatlas/analysis/ast/pipeline.py`, `src/marketatlas/analysis/graph.py`
