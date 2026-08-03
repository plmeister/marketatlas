# 057: DSL Parser — DSL Text to Template AST

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Recursive-descent parser converting DSL text (055 grammar, 056 token stream) into a template `Analysis` — the exact AST the compiler pipeline (051) accepts. Output contains literal params, list literals, `ChoiceExpression` nodes, and `Binding`s from shorthand/reference fields. Expansion is NOT performed here (that is pipeline stage 2, backlog 050).

## Scope

- Parse `name := Type { fields }` → `Definition(name, provider=resolved_type)`
- Resolve `Type` via the default registry (capability → provider) per 055 decision
- Fields:
  - `name: expr` → `Parameter(name, expr)`
  - shorthand `name,` → `Binding` per 055 expansion rule, using provider input metadata (058)
  - `name: reference,` → `Binding(source, output, target, input)` per 055
- Expressions: literal (int/float/string/bool/null), list `[...]`, choice `<...|...>` → `ChoiceExpression` (048)
- Unknown `Type` / unknown capability → positioned error (059)
- Duplicate definition names → error (consistent with builder.py:69)
- Produce full `Analysis` with `providers` populated from the registry so the template is self-contained and serializable (046-compatible)

## Acceptance Criteria

- [ ] All spec examples parse to ASTs equal to builder-constructed equivalents (047/048 shapes)
- [ ] Template AST keeps `ChoiceExpression` nodes intact — no expansion here
- [ ] Shorthand `dependency,` produces a Binding; parameter `name: value` produces a Parameter (disambiguation per 055/058)
- [ ] List `[1, 2, 3]` parses as a literal list param — never a choice (048 rule)
- [ ] Unknown `Type` → positioned error naming the capability; available capabilities listed
- [ ] Duplicate definition names → error
- [ ] Error messages carry line/col via 059
- [ ] Round-trip: parsed AST serializes via `to_json` (039) and matches snapshots of equivalent builder output
- [ ] Tests: per-construct parse tests, error paths, full multi-definition template

## Technical Notes

- Parser may target the construction API (053) or construct AST nodes directly — decide in 053/057; prefer emitting nodes directly to keep the parse path single-purpose.
- Keep parse pure: no registry side effects; registry is passed in or imported default.

## Related

- Backlogs 055, 056 (prereq), 058 (provider inputs for shorthand), 059 (errors), 050 (expansion), 051 (pipeline entry)
- Future: DSL supersedes the YAML loader (`strategy/loader.py`); retirement out of scope
