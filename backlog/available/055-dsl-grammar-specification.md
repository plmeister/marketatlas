# 055: DSL Grammar Specification

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Formal grammar specification for the analysis DSL, pinned down from the draft spec. The DSL is declarative and concise: it specifies provider instances, parameter values, dependency selection where ambiguous, and template variation points. Everything else — graph structure, dependencies, execution order, deduplication, optimisation — is inferred by the compiler.

The grammar is the contract every other DSL backlog (056-060) and the pre-req AST backlogs (047-054) feed.

## Constructs (from the draft spec)

- Definitions: `name := Type { ... }` — instantiates a provider
- Fields: `parameter: value,` or shorthand dependency `dependency,` → `dependency: dependency` (when the provider defines an input of that name)
- Trailing commas always permitted
- Expressions: Literal, Reference, List `[...]`, Choice `<a | b | c>`
- Choices are compile-time expansion points (AST construct, not runtime); lists are ordinary data values, never expansion

## Design Decisions to Resolve (with rationale)

- **`Type` mapping**: resolve `Type` as a registry capability key (`ema`, `atr`, `trend`, `swings`, `sr`, ...) via `create_default_registry` — concise, decouples DSL from class names. `registry.resolve()` currently picks the first of multiple providers per capability (registry.py:88); the grammar must not rely on multi-provider capability ordering.
- **Shorthand vs parameter disambiguation**: a field whose name matches a provider input → dependency binding; otherwise → parameter. Requires provider input metadata (backlog 058). Rule stated explicitly in the grammar.
- **Provider-selection choice** (`provider: <ZigZag | WilliamsFractal>` in the draft): ambiguous in the spec — could be a param named `provider` or definition-level type selection. Default decision: support choice only over parameter values initially; definition-level `name := <A | B> { ... }` deferred. Document this.
- **Timeframe**: NO reserved field. Timeframes are ordinary definitions via a `TimeFrame` provider (`tf1w := TimeFrame { resolution: 1w }`), referenced by analysis nodes (`timeframe: tf1w`). Grammar decision owned by 061; EBNF stays generic (this is just a definition + a reference).
- **Group scoping**: `group` scope marker + spanning references (syntax owned by 064). Deferred here — record the placeholder in EBNF as a decision point.
- **Reference expression**: `dependency: dependency` maps to a `Binding` at parse time (source/output/target/input). Extended by 061: a reference to a value-producing definition (a `TimeFrame` def, category `timeframe`) is VALUE SUBSTITUTION (compile-time), not a runtime fact binding. Compiler disambiguates by provider category. No new AST expression node needed initially — decide during grammar work and document.
- **Literals**: int, float, string, bool, null; list `[...]`; choice `<a|b|c>`.
- **Comments/whitespace**: whitespace-insensitive (braces/commas delimit); recommend `//` line comments — decide in grammar.

## Acceptance Criteria

- [ ] Grammar doc at `docs/dsl.md` (or `docs/ast/dsl.md`), EBNF + examples
- [ ] Every grammar rule has at least one example (valid + invalid where useful)
- [ ] All design decisions above resolved with rationale; open questions explicitly listed
- [ ] Mapping table: DSL construct → AST node (Definition, Parameter, Binding, Expression)
- [ ] Draft-spec examples transcribed into the doc verbatim and annotated
- [ ] Documented relationship to the compiler pipeline: DSL → template AST (057) feeds stage 1 of backlog 051

## Technical Notes

- No new dependencies: hand-rolled lexer (056) + recursive-descent parser (057) match the zero-dep project style (pyproject.toml has no parser libs).
- Keep the grammar YAML-independent; the YAML loader is a legacy path that the DSL eventually supersedes (retirement is out of scope here).

## Related

- All DSL backlogs 056-060
- Backlogs 061 (timeframe as definition), 064 (group scoping) — grammar extensions owned there
- Backlog 044 (semantic model doc — concepts this grammar references)
- Backlogs 047-054 (pre-reqs: expression hierarchy, choices, expansion, pipeline stages, provider metadata)
