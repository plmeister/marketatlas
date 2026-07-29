# 046: Snapshot Tests for Compiled Analyses

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Snapshot tests that build small analyses (EMA, Trend, ATR, Pullback, 4-swing) via the builder, compile them, and snapshot the resulting AST and compiled graph. Makes future refactoring safe — changes to model, compiler, or passes produce visible diff.

## Acceptance Criteria

- [ ] Snapshot tests for: single analyzer (EMA(20)), linear chain (EMA→Trend), branching (EMA+ATR→Pullback), full strategy
- [ ] Each test snapshots: builder construction code, final AST (JSON), compiled `AnalysisGraph` structure
- [ ] Snapshot format: inline in test file (via `pytest-snapshot` or similar), or JSON files in `tests/snapshots/`
- [ ] CI: snapshot update requires explicit `--update-snapshots` flag
- [ ] Tests document what each analysis does in plain English
- [ ] Verify deteminism: same builder code produces same AST every time

## Technical Notes

- Use `pytest-snapshot` or `syrupy` for snapshot testing
- AST snapshot: `analysis.to_json()` output
- Graph snapshot: list of nodes, edges, topological order
- Consider markers to skip snapshot update on minor version bumps

## Related

- All AST backlogs (036-045)
- Backlog 040: Compiler adapter
