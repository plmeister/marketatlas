# 063: Instrument Runtime Expansion

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Make the compiled graph instrument-agnostic: the DSL/AST describes a template over one implicit instrument; the runtime supplies the instrument list to instantiate against. Instruments are an expansion point OUTSIDE the DSL — DSL text never names an instrument. One template → N per-instrument graphs.

Today the whole pipeline is single-instrument: `ASTCompiler.compile` produces one `AnalysisGraph`, backtests run one symbol (cli.py). Instantiation must not bake instruments into the AST; instead the compiled template graph is parameterized by instrument and the runtime materializes per-instrument instances.

## Scope

- Conceptually split: concrete AST (choice-expanded, 051) → instrument-neutral template graph → per-instrument `AnalysisGraph`
- Instantiation API: `TemplateGraph.instantiate(instrument) -> AnalysisGraph` or `compile(analysis, instruments) -> tuple[AnalysisGraph, ...]` (decide; prefer explicit multi-graph return per 051 convention)
- Instrument identity via `Instrument`/registry (033); symbol/timeframe resolved per instrument
- Each per-instrument graph runs isolated; facts keyed per instrument (no cross-contamination)
- Execution entry: backtest/run accepts instrument list, instantiates per instrument

## Non-Goals

- No cross-instrument nodes (backlog 064)
- No data requirements inference (065) — this defines the runtime model only
- No DSL syntax for instruments (principle: runtime supplies them)

## Acceptance Criteria

- [ ] One template AST compiles to N isolated per-instrument graphs
- [ ] Instantiation is cheap and repeatable (template compiled once)
- [ ] Instruments list passed at run time; empty list → error
- [ ] Existing single-instrument backtests unchanged (default = one instrument)
- [ ] Facts/results namespaced per instrument
- [ ] Tests: multi-instrument backtest, isolation, instantiation identity

## Technical Notes

- Do not introduce `Instrument` into AST nodes; keep the separation the user stated: expansion point outside the DSL.
- Reuse `StrategyBundle` merge ideas (backtesting) if a combined run is needed — but per-graph isolation is the default.

## Related

- Backlog 033 (instrument registry), 065 (data requirements), 064 (group expansion builds on this)
- `src/marketatlas/backtesting/`, `src/marketatlas/cli.py`
