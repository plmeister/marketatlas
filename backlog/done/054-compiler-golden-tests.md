# 054: Compiler Golden Tests — Choice Expansion

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Golden tests — explicit inline expected outputs, not file snapshots — covering choice expansion and compilation, operating purely on ASTs. These pin the exact behaviour specified across backlogs 048/050/051 (single, nested, multiple choices; list literal vs choice; empty-choice error; duplicate definitions after expansion) and protect against regressions as the compiler evolves.

## Scope

- Test matrix (all AST-level, no registry/graph snapshots):
  - single choice: `Choice([50, 100])` → 2 concrete ASTs, exact param values asserted
  - nested choice: flattened cartesian product asserted
  - multiple choice params (same and different definitions): product count + values asserted
  - list literal `[50, 100]` vs `Choice([50, 100])`: list stays a single AST, choice expands
  - empty choice: `CompilationError` naming definition + param
  - duplicate definitions post-expansion: two choices converging to the same concrete AST → reported as duplicate (per 051 stage 3)
- Each test asserts the full expected `Analysis` (via `to_json` comparison or field-level asserts)
- Runs against `Pipeline.expand` and stage-3 validation, not the full graph pipeline

## Non-Goals

- No graph/execution snapshots (those are backlog 046)
- No YAML-parser tests

## Acceptance Criteria

- [ ] Golden cases above implemented with exact expected outputs
- [ ] Empty-choice and duplicate-definition error paths asserted (message includes definition + param)
- [ ] Deterministic: same input → same output every run (product ordering defined per 050)
- [ ] Changes to 047-051 that break expansion behaviour are caught by these tests

## Technical Notes

- Product ordering must be deterministic and documented (backlog 050: choices iterate in declaration order, definition order preserved) so golden asserts are stable.
- Prefer explicit `assert expanded == expected` on canonical AST equality over JSON string comparison to avoid dict-order noise.

## Related

- Backlog 046 (existing graph snapshots), 048 (choice semantics), 050 (expansion), 051 (pipeline)
