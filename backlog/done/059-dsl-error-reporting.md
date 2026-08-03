# 059: DSL Error Reporting — Positioned Diagnostics

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Positioned diagnostics for the DSL. Lexer/parser errors (056/057) and downstream compiler errors must carry source location (line, col) so a broken DSL file produces actionable messages. The current `Diagnostic` (validation.py:15) has `message`/`severity`/`node_name`/`node_type` but no source position; `CompilationError` (pipeline.py:136) surfaces messages without location.

## Scope

- Source location model: line/col (1-based) + span, shared by lexer (056), parser (057), and validation/compiler errors
- Extend `Diagnostic` with optional source location; lexer/parser emit positioned diagnostics
- Formatted output: `line:col: error: message` + source snippet with caret (or a compact single-line form for tests)
- `CompilationError` preserves positions when raised from parse/validation; expansion errors (050) attach positions where known

## Acceptance Criteria

- [ ] Lexer errors include line/col (unterminated string, illegal char, truncated `:=`)
- [ ] Parser errors include line/col (unknown Type, unexpected token, duplicate name)
- [ ] `Diagnostic` carries optional position; existing validation tests unchanged (field optional)
- [ ] Compact formatter: `line:col: <severity>: <message>` — one line per diagnostic
- [ ] Snippet rendering includes the offending line and caret (used in CLI, not asserted byte-for-byte in unit tests)
- [ ] `CompilationError` from pipeline stages preserves positions where source-mapped
- [ ] Tests: position accuracy for representative errors; multi-error reporting

## Non-Goals

- No IDE/LSP integration
- No partial-parse recovery beyond "collect errors at a point and abort cleanly"

## Technical Notes

- Keep the model small: `SourcePosition(line: int, col: int)` (+ optional `end`). Extend with span only if a consumer needs it.
- Position model decided here is reused by 056 — do this decision first.

## Related

- Backlog 056 (lexer positions), 057 (parser errors), 051 (pipeline error surfacing)
- `src/marketatlas/analysis/ast/validation.py` (Diagnostic), `pipeline.py` (CompilationError)
