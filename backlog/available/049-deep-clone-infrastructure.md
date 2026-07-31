# 049: Deep Clone Infrastructure for AST Nodes

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Provide a deep-copy mechanism for the AST so transformation passes (backlog 050 expansion, later rewriting passes) can produce modified copies without mutating shared node objects. Frozen dataclasses give shallow safety, but `Parameter.value`/expression trees can still carry mutable payloads; cloning must be explicit and predictable.

## Scope

- `clone(node)` (or `node.clone()` methods) covering `Analysis`, `Definition`, `Parameter`, `Binding`, `Provider`, and all `Expression` types
- Recursive clone of nested expression trees
- Preservation of `id`/`metadata`

## Non-Goals

- No mutation-based API — AST stays immutable
- No partial replace-on-path helpers yet (add when a pass needs them)

## Acceptance Criteria

- [ ] `clone(Analysis(...))` returns an equal, independent AST: mutating a clone's payload or replacing a field does not affect the original
- [ ] Nested `ChoiceExpression`/`LiteralExpression` subtrees fully independent after clone
- [ ] Works for definitions with `id`/`metadata` and providers with `default_params`
- [ ] Cloning a pure-literal AST is semantically a no-op (round-trip equal)
- [ ] Unit tests: identity independence for every node type; nested expression independence

## Technical Notes

- `copy.deepcopy` on frozen dataclasses works but silently couples clone semantics to field types; an explicit recursive clone keeps expansion output predictable and testable.
- Return-type stability: every `clone` returns the same static type as its input.

## Related

- Backlog 047/048: expression nodes being cloned
- Backlog 050: expansion pass is the first consumer
