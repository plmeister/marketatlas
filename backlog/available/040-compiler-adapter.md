# 040: Compiler Adapter — AST to Graph

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Adapter that converts the AST into the existing graph compilation input. Bridges new semantic model to current execution pipeline without changing runtime behavior.

## Acceptance Criteria

- [ ] `ASTCompiler.compile(analysis: Analysis) -> AnalysisGraph` produces same `AnalysisGraph` as current YAML path
- [ ] Same analyzers registered, same topological sort, same dedup
- [ ] Signal configs and risk configs extracted from AST definitions
- [ ] Identical behavior for identical analyses (parity test)
- [ ] No changes to existing execution pipeline
- [ ] Existing YAML loader can optionally produce AST internally for migration path

## Technical Notes

- Current entry point: `StrategyConfig` loaded from YAML → `build_analyzers()` → `AnalysisGraph`
- Adapter reads AST definitions, creates same `AnalyzerConfig`/`SignalConfig`/`RiskConfig` objects
- Existing tests pass without modification
- Can be verified by building equivalent analyses via AST and YAML, comparing graph output

## Related

- Backlog 036: AST model
- Backlog 037: Builder API
- `src/marketatlas/config/loader.py` — current YAML loader
- `src/marketatlas/analysis/graph.py` — AnalysisGraph
