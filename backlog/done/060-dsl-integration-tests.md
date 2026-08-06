# 060: DSL Integration Tests — Text to Graph

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

End-to-end golden tests running the full path: DSL text → lexer (056) → parser (057) → template AST → pipeline (051: validation, choice expansion 050, concrete validation, graph compilation) → `AnalysisGraph`. Anchors the whole DSL feature to the draft spec examples and to backlog 054's choice-expansion behaviour, operating at the text level rather than the AST level.

## Scope

- Fixtures: DSL text from the spec examples (single def, linear chain, branching, full strategy; choice params; list params; shorthand bindings)
- Assertions per fixture:
  - parsed template AST (equality with expected, per 057)
  - expansion output count + concrete ASTs (per 050/054 semantics)
  - final `AnalysisGraph` structure for literal-only fixtures
  - error paths: empty choice, unknown Type, duplicate definitions post-expansion, unknown param (052), positioned messages (059)

## Acceptance Criteria

- [ ] Spec examples parse → expand → compile successfully; graphs match builder-equivalent references
- [ ] Choice fixtures: single/nested/multiple choices produce exact expansion counts (cartesian), matching 054 golden expectations
- [ ] List literal fixture: one concrete AST, list intact
- [ ] Shorthand dependency fixture: bindings correct, graph edges match
- [ ] Error fixtures assert message + line/col
- [ ] Deterministic: same DSL text → same output every run
- [ ] Tests organised so each pipeline stage is exercised and stage boundaries are visible in test names

## Non-Goals

- No new parser features (055-058 own those)
- No YAML-loader comparisons

## Technical Notes

- Reuse fixtures style from 046 snapshots; prefer explicit asserts over file snapshots for expansion-count logic (per 054), snapshots optional for full-graph structure.
- Regression gate: any change to 047-058 that breaks a spec example is caught here.

## Related

- Backlogs 055-059 (prereq), 050 (expansion), 051 (pipeline), 054 (golden choice tests)
- `tests/test_ast_*.py` — existing AST test layout
