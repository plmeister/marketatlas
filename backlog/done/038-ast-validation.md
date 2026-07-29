# 038: AST Validation — Semantic Checks

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Semantic validation over the AST before compilation. Catches structural errors early with clear diagnostics.

## Validation Rules

- [ ] Duplicate definition names → error
- [ ] Unknown definition references in bindings → error (source/target must exist)
- [ ] Invalid bindings: cycle detection (A→B→A) → error
- [ ] Missing required parameters on known impl types → warning
- [ ] Unused definitions (no bindings reference them) → warning
- [ ] Self-referencing bindings → error
- [ ] Unknown `type` field value → error (must be one of: analyzer, signal, risk, transformer)
- [ ] All errors include line/path context for debugging

## Acceptance Criteria

- [ ] `ValidationResult` dataclass: `is_valid: bool`, `errors: list[Diagnostic]`, `warnings: list[Diagnostic]`
- [ ] `validate(analysis: Analysis) -> ValidationResult`
- [ ] Invalid ASTs fail with clear error messages
- [ ] Valid ASTs produce valid result with no errors
- [ ] Diagnostics include: message, severity, node reference

## Related

- Backlog 036: AST model
- Backlog 037: Builder API
