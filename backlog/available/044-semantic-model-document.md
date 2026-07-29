# 044: Semantic Model Document

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Concise reference document defining all concepts in the semantic model: Analysis, Definition, Binding, Capability, Provider, Fact, FactKey. Becomes the reference for future contributors and agents (including LLM-driven development).

## Acceptance Criteria

- [ ] Document in `docs/semantic-model.md` (or `docs/ast/README.md`)
- [ ] Defines each concept with purpose, constraints, and example
- [ ] Explains relationships between concepts (e.g. "A `Definition` references a `Provider` that implements a `Capability`")
- [ ] Includes lifecycle: AST → Validation → Compilation → Execution
- [ ] Includes naming conventions and best practices
- [ ] Diagrams (ASCII or Mermaid) showing concept relationships
- [ ] Updated as the model evolves (keep in sync with code)

## Related

- All AST backlogs (036-050)
- `src/marketatlas/analysis/` — existing analyzers
