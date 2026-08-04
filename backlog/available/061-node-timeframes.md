# 061: TimeFrame as Value-Producing Definition

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Timeframes are first-class definitions, not a reserved DSL field. The DSL stays small: `TimeFrame` is an ordinary definition producing a timeframe value, and analysis nodes reference it through the normal parameter/reference syntax.

```dsl
tf1w := TimeFrame { resolution: 1w }
tf1d := TimeFrame { resolution: 1d }

swings := Swings { timeframe: tf1w }
trend  := Trend  { timeframe: tf1d }
```

The DSL never knows the instrument it runs against — it only declares which timeframes the analysis needs. The runner collects every `TimeFrame` definition in use, derives the required TF set, and ensures data is fetched before execution (backlog 065).

Today `Definition` (models.py:46) has no timeframe at all: `_ast_to_config` (pipeline.py:203-231) builds `AnalyzerConfig` without one, so AST-compiled analyzers run at the strategy base timeframe. The execution layer already supports per-analyzer timeframes — `Analyzer.timeframe` (base.py:12), `FactKey.timeframe` (factkey.py:13), per-analyzer view selection (graph.py:87-90).

## Scope

- `TimeFrame` provider in the registry: category `timeframe`, param `resolution` (a `Timeframe` literal). Fits the existing category scheme alongside analyzer/signal/risk (pipeline.py:216-222)
- Value-producing semantics: a `TimeFrame` definition produces a compile-time value, NOT a runtime fact. It is resolved during compilation and excluded from the execution graph
- Compiler resolution pre-pass: after choice expansion (050), resolve all in-use `TimeFrame` definitions → `name → Timeframe` map, propagate to `AnalyzerConfig.timeframe` (config.py:11); `TimeFrame` defs never become analyzers
- Reference semantics extension (055): a reference to a `TimeFrame` definition is value substitution (compile-time); a reference to an analyzer definition remains a binding/fact dependency (runtime). Compiler disambiguates by provider category
- Choice over timeframes (`timeframe: <tf1w | tf1d>`) → per-timeframe template expansion via 048/050
- Default: node with no `timeframe` reference → strategy base timeframe (decision: a designated base `TimeFrame` def vs provider default — resolve in 058)
- Serialization round-trip (039 format)
- Validation: `resolution` must be a valid `Timeframe`; unknown/empty → error

## Non-Goals

- No cross-timeframe reference wiring (backlog 062)
- No data-fetch inference (backlog 065)
- No instrument runtime context (backlog 063)

## Acceptance Criteria

- [ ] `TimeFrame` provider registered; a `TimeFrame` definition serializes round-trip
- [ ] `swings := Swings { timeframe: tf1w }` + `trend := Trend { timeframe: tf1d }` compile; `AnalysisGraph.run` selects per-analyzer views (045 behaviour confirmed)
- [ ] Timeframe references resolve to `Timeframe` values and set `AnalyzerConfig.timeframe`; `TimeFrame` defs absent from the execution graph
- [ ] Reference-to-TimeFrame is value substitution; reference-to-analyzer stays a binding (055 disambiguation)
- [ ] Choice over timeframes expands into per-timeframe concrete ASTs (golden pattern, 054)
- [ ] Unused `TimeFrame` definition (declared, never referenced) → unused-definition warning; the existing unused-check (validation.py:171) must count param references as "used"
- [ ] Invalid `resolution` → positioned error (059)
- [ ] Tests: model/serialization, compile+run, choice-over-timeframe, unused-TF warning, validation

## Technical Notes

- The resolution pre-pass runs AFTER choice expansion: a Choice over timeframes is itself an expansion, so each concrete AST has fixed `TimeFrame` references.
- Existing YAML path unchanged (loader.py:77,165) — this applies to the AST/DSL path only.
- `TimeFrame` defs stay in the template AST (so the runner can collect them); they're pruned at graph generation.

## Related

- Backlog 048/050 (Choice over timeframes), 055 (grammar: reference-to-value), 058 (provider contract: `timeframe` input + base default), 062 (cross-TF refs), 065 (data requirements — collects in-use `TimeFrame` defs)
- Backlogs 045 (multi-resolution MarketView), 046 (multi-TF data fetching) — existing execution + fetch layer
- `src/marketatlas/analysis/ast/models.py`, `pipeline.py`, `registry.py`
