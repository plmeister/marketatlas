# 088: Prune low-value tests and reduce test count

**Status:** pending
**Epic:** testing
**Priority:** medium
**Depends on:** none

## Description

1,450 tests with a 1.8:1 test-to-source ratio. Several test files test edge
cases of rarely-changing code. Prune tests that:

- Test DSL lexer tokenization edge cases (lexer rarely changes)
- Validate HTML structure (fragile, breaks on cosmetic changes)
- Test interactive renderer pixel-level output (lowest-value rendering)
- Duplicate coverage already provided by integration tests

Estimated removable: ~130 tests / ~3,000 lines.

## Candidates for pruning

| File | Tests | Lines | Rationale |
|------|-------|-------|-----------|
| `test_dsl_lexer.py` | 36 | 347 | Lexer tokens are tested indirectly by parser + integration tests |
| `test_html_output_validation.py` | 31 | 711 | HTML structure checks break on layout changes, not logic bugs |
| `test_interactive_renderer.py` | 69 | 1,203 | Tests chart rendering output — visual regression, not functional |
| `test_ast_golden_expansion.py` | 10 | 318 | Golden file tests — useful but brittle; keep 3 representative cases |

## Design

1. **Remove `test_dsl_lexer.py`** — parser tests (test_dsl_parser.py: 47
   tests) already cover token semantics; raw token tests add no signal.
2. **Remove `test_html_output_validation.py`** — replace with 5 smoke tests
   in `test_html_renderer.py` that verify HTML contains key sections
   (title, chart div, trade table).
3. **Remove `test_interactive_renderer.py`** — interactive rendering is
   tested by the JS test suite (51 tests in `tests/js/`). Python-side
   tests just verify dict structure, which the JS tests already cover.
4. **Trim `test_ast_golden_expansion.py`** from 10 → 3 tests (one per
   expansion category: choice, group, implicit-ref).
5. **Keep `test_risk_engine.py` (37 tests), `test_tradebook.py` (29),
   `test_backtester.py` (31)** — these are critical-path tests.

## Acceptance Criteria

- [ ] Total test count reduced from ~1,450 to ~1,310
- [ ] Total test lines reduced from ~21,750 to ~18,750
- [ ] No critical-path test removed (risk, tradebook, backtester, signal)
- [ ] `pytest tests/` passes, coverage % does not drop on strategy/backtesting
- [ ] `test_html_renderer.py` gains 5 smoke tests to compensate

## Related

- `tests/test_dsl_lexer.py` (36 tests, 347 lines)
- `tests/test_html_output_validation.py` (31 tests, 711 lines)
- `tests/test_interactive_renderer.py` (69 tests, 1,203 lines)
- `tests/test_ast_golden_expansion.py` (10 tests, 318 lines)
