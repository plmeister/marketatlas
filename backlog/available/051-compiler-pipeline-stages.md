# 051: Compiler Pipeline Stages — Restructured Compilation

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Restructure the compilation pipeline into four explicit stages matching the intended architecture:

```
AST (template) → [1 AST validation] → [2 template expansion] → [3 concrete AST validation] → [4 graph compilation]
```

Today the pipeline (pipeline.py) runs Validation → RegistryResolution → DefinitionExpansion → GraphGeneration, with default-param merging duplicated across the resolution pass (pipeline.py:71) and the expansion pass (pipeline.py:106). Stage 2 expands choices (backlog 050; identity until then). Stage 3 validates the post-expansion AST (duplicate definitions after expansion, all params literal — details in 052/054). Stage 4 is the existing graph generation. The `Parse` stage (DSL text → template AST) sits upstream of stage 1 and is owned by the DSL backlogs (057).

## Scope

- Rename/reorder passes to the four-stage model
- Remove the redundant default-param merge — single owner (registry resolution)
- Pipeline contract for multi-output expansion: `run(analysis) -> AnalysisGraph` must keep working for single-concrete-AST inputs; add an expansion-aware entry point (e.g. `Pipeline.expand(analysis) -> tuple[Analysis, ...]` and/or `compile_all -> tuple[AnalysisGraph, ...]`) so multiple concrete ASTs are explicit rather than merged implicitly
- Stage 3 runs per concrete AST (duplicate definitions can only be detected post-expansion)
- Backward compat: `ASTCompiler.compile` single-graph path unchanged for choice-free ASTs

## Acceptance Criteria

- [ ] Pipeline exposes stages named/ordered: AST validation → template expansion → concrete AST validation → graph compilation
- [ ] Default-param merge happens in exactly one place
- [ ] `ASTCompiler.compile` unchanged for literal-only ASTs (existing compiler tests + 046 snapshots pass)
- [ ] `Pipeline.expand` returns concrete ASTs using backlog 050
- [ ] Stage 3 runs on each concrete AST; duplicate definitions (054) reported
- [ ] Running a subset of stages for debugging still supported (per backlog 045, incl. `run_to_ast`)
- [ ] Tests: each stage in isolation, multi-output path, choice-free regression

## Technical Notes

- Backlog 045 established `CompilerPass`/`Pipeline`; this reorders and fills in stages 2/3. Preserve the existing interface.
- Multiple concrete graphs: return a `tuple` — do not silently merge into one `AnalysisGraph`; merge semantics belong to the caller (see `StrategyBundle`).

## Related

- Backlog 045 (existing passes), 050 (expansion), 052 (validation), 054 (golden tests)
- Backlog 057: DSL parser — feeds stage 1 (template AST)
- `src/marketatlas/analysis/ast/pipeline.py`, `compiler.py`
