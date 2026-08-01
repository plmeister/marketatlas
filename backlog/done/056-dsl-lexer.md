# 056: DSL Lexer

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Tokenizer for the analysis DSL (grammar: backlog 055). Produces a token stream with source positions consumed by the recursive-descent parser (057) and positioned diagnostics (059).

## Token Set

- Structural: `:=`, `{`, `}`, `:`, `,`, `[`, `]`, `<`, `|`, `>`
- `IDENT` — definition names, field names, Type/capability names, references
- `NUMBER` — int and float
- `STRING` — quoted string literals
- `COMMENT` (if adopted in 055) — skipped, but token positions must account for it
- Whitespace-insensitive; newlines not significant (braces/commas delimit)

## Acceptance Criteria

- [ ] Lexer returns ordered tokens with line/col position each (for 059)
- [ ] All token types from the 055 grammar implemented
- [ ] Int vs float distinguished; string escapes handled
- [ ] Malformed input → `DslSyntaxError` with position: unterminated string, illegal character, truncated `:=`/`|`/`<`
- [ ] Comments and whitespace skipped correctly; empty input → empty token stream
- [ ] Round-trip property: concatenating token lexemes reproduces source modulo whitespace/comments
- [ ] Tests: token tables for grammar examples, error cases, position accuracy

## Non-Goals

- No parsing/grammar structure (057)
- No AST construction

## Technical Notes

- Keep a single-pass scanner, maximal-munch; no external deps (per 055).
- Position model shared with 059: (line, col) 1-based, byte or char offset — decide in 059 and reuse here.

## Related

- Backlog 055 (grammar), 057 (parser consumes), 059 (positions/diagnostics)
