# 062: Cross-Timeframe References — Binding Semantics

**Status:** pending  
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

- [ ] `trend@1d ← swings@1w` style analysis compiles; `AnalysisGraph.run` selects correct views per node
- [ ] Single-timeframe analyses (existing 046 snapshots) compile unchanged — bindings additive, not breaking
- [ ] Reference to unknown definition → error; reference whose output isn't declared by provider (058) → error
- [ ] Cross-TF reference without explicit declaration → error (or auto-declared per 055 decision — document whichever)
- [ ] Signal `requires` includes source timeframe
- [ ] Tests: cross-TF wiring, resolution errors, contract mismatches, graph run correctness

## Technical Notes

- This is where the DSL `Reference` expression (055) meets the AST `Binding` — decide whether parser emits bindings with explicit source/TF or the compiler infers it from definition lookup.
- Watch `_ast_to_config` (pipeline.py:203): it currently drops analyzer bindings; the compiler-side wiring is the core change.

## Related

- Backlog 061 (node timeframes — prereq), 058 (provider contracts), 055 (Reference expression), 045 (view selection)
- `src/marketatlas/analysis/ast/pipeline.py`, `src/marketatlas/analysis/graph.py`
