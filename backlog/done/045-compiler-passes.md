# 045: Compiler Passes — Explicit Compilation Stages

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Split compilation into explicit, testable stages. Each pass transforms or validates the AST one step closer to an executable graph. Existing graph compiler remains largely unchanged behind this interface.

## Compilation Stages

```
AST → [Pass 1: Validate] → [Pass 2: Resolve bindings] → [Pass 3: Expand definitions] → [Pass 4: Generate graph]
```

- **Pass 1 — Validate**: run semantic checks (backlog 038). Abort on errors.
- **Pass 2 — Resolve bindings**: convert symbolic definition names to provider references via registry. Resolve `FactKey` identities.
- **Pass 3 — Expand definitions**: inline default parameters from provider registry. Flatten inheritance/composition.
- **Pass 4 — Generate graph**: produce existing `AnalysisGraph` from expanded AST. Reuse current topological sort and dedup.

## Acceptance Criteria

- [ ] `CompilerPass` interface: `run(ast: Analysis) -> Analysis`
- [ ] `Pipeline` class: `add_pass(pass)`, `run(ast) -> AnalysisGraph`
- [ ] Each pass produces intermediate AST (conceptually — may be lazy)
- [ ] Passes composable: can run subset for debugging
- [ ] Existing YAML path unchanged (may delegate to same pipeline internally)
- [ ] Diagnostic output per pass (what changed, what was resolved)
- [ ] Tests: each pass in isolation with known input → expected output

## Related

- Backlog 038: Validation
- Backlog 040: Compiler adapter (will use pipeline)
- `src/marketatlas/analysis/graph.py` — existing compiler
