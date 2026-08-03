# 061: Timeframe Declaration on Analysis Nodes

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Let AST definitions declare the timeframe they operate on, and the DSL express it. Today `Definition` (models.py:46) has no timeframe: `_ast_to_config` (pipeline.py:203-231) builds `AnalyzerConfig` without one, so every AST-compiled analyzer runs at the strategy base timeframe. The execution layer already supports per-analyzer timeframes — `Analyzer.timeframe` (base.py:12), `FactKey.timeframe` (factkey.py:13), per-analyzer view selection in `AnalysisGraph.run` (graph.py:87-90), `StrategyConfig.timeframes` (config.py:31). Elevate that into the AST so the DSL and compiler are timeframe-aware.

## Scope

- `Definition.timeframe: Timeframe | None` (`None` = strategy base timeframe)
- `Analysis.timeframes: tuple[str, ...]` — declared TF set; base timeframe is `timeframes[0]`
- Builder: `.with_timeframe("1h")` on definition builder; base TF set at `AnalysisBuilder`
- Serialization round-trip (039 format)
- `_ast_to_config` sets `AnalyzerConfig.timeframe`
- Validation: timeframe value must be a valid `Timeframe`; unknown/empty → error
- DSL: reserved `timeframe` field per definition (`ema := EMA { timeframe: "1h", period: 20 }`) — extends 055 grammar (see patch note)

## Non-Goals

- No cross-timeframe reference semantics (backlog 062)
- No data-fetch inference (backlog 065)

## Acceptance Criteria

- [ ] `Definition.timeframe`/`Analysis.timeframes` in model; AST round-trip preserves both
- [ ] Builder fluent API for both; existing builder tests unchanged for default (`None`)
- [ ] Compiled analyzers get correct `timeframe`; `AnalysisGraph.run` selects per-analyzer view (045 behaviour confirmed via existing multi-TF analyzers)
- [ ] DSL field parses (057) and produces equal AST to builder equivalent
- [ ] Validation rejects invalid timeframe values with positioned error (059)
- [ ] Tests: model, serialization, builder, compile, DSL, validation

## Technical Notes

- Mirror the existing YAML semantics: `timeframe` per analyzer, base TF default (loader.py:77,165).
- FactKey already encodes timeframe (`tf_1d` suffix, factkey.py:19) — node timeframe flows into produced FactKeys automatically via base.py:28.

## Related

- Backlog 055 (grammar: `timeframe` field — patch pending), 062 (cross-TF refs), 065 (data requirements)
- Backlogs 045 (multi-resolution MarketView), 046 (multi-TF data fetching) — existing execution + fetch layer
- `src/marketatlas/analysis/ast/models.py`, `builder.py`, `serialization.py`, `pipeline.py`
