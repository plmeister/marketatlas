# 064: Market Groups — Cross-Instrument Nodes

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Analyse instrument sets as a unit — e.g. linked forex pairs to estimate dollar strength. A group is a named collection of instruments supplied by the runtime (like instruments, 063: outside the DSL). Group-scoped nodes consume outputs of per-instrument sibling nodes across the whole group: one node instance wiring together N per-instrument instances.

Example: for a group of pairs, a `DollarStrength` node aggregates the relative-strength output of the per-pair `RelativeStrength` nodes. Template shows one pair node + one group node; instantiation produces N pair nodes + 1 group node wired to all N.

## Scope

- Node scope marker: per-instrument (default) vs group — AST field or DSL marker (decide with 055: e.g. `group := ...` keyword or `scope: group` field)
- Spanning reference: a group node references a per-instrument definition across all group members (wildcard semantics)
- Instantiation (extends 063): per-instrument nodes → N copies; group node → 1, wired to all member copies
- Group membership supplied at runtime; identity via `InstrumentRegistry`
- Validation: group node inputs must be outputs of group-member scoped nodes; no cross-group references

## Non-Goals

- No cross-group references or nested groups (future work)
- No dynamic membership during a run
- No aggregation semantics — providers own that (group node is just a node whose inputs span the group)

## Acceptance Criteria

- [ ] DSL/API can declare a group-scoped node and its spanning references
- [ ] Instantiation: N per-instrument copies + 1 group node wired to all N (verified structure)
- [ ] Group node sees per-member facts (dollar-strength-style provider works end to end)
- [ ] Validation rejects invalid spanning references and cross-group refs
- [ ] Runtime supplies group membership; empty group → error
- [ ] Tests: group wiring structure, end-to-end 2-3 instrument group, validation errors

## Technical Notes

- The spanning reference is the one place the DSL references something "collective" — this is the syntax decision to pin in 055 before building.
- Keep group nodes data-free: they consume facts, never fetch market data directly (feeds 065: group adds no direct fetch, union of members).

## Related

- Backlog 063 (instrument instantiation — prereq), 061 (node timeframes), 062 (references), 065 (data union)
- `src/marketatlas/data/` (instrument registry), 033
