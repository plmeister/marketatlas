# 089: Split tests into tiers for faster agent feedback

**Status:** pending
**Epic:** testing
**Priority:** high
**Depends on:** 088

## Description

1,450 tests take ~16 seconds. An agent making a strategy change shouldn't
wait for DSL lexer edge cases. Split into three tiers with independent
run targets.

## Tiers

### Tier 1 — Critical (~200 tests, ~2s)

Tests that verify the core data pipeline. Run on every edit.

Files:
- `test_risk_engine.py` (37)
- `test_tradebook.py` (29)
- `test_backtester.py` (31)
- `test_signal_system.py` (27)
- `test_pullback_confirmed_entry.py` (25)
- `test_portfolio_backtester.py` (18)
- `test_portfolio.py` (18)
- `test_strategy_bundle.py` (13)
- `test_analysis.py` (38 — analyzer correctness)

Total: ~226 tests

### Tier 2 — Integration (~500 tests, ~6s)

Tests that verify DSL compilation, data store, and CLI. Run before PR merge.

Files:
- `test_ast_pipeline.py` (28)
- `test_ast_validation.py` (31)
- `test_ast_compiler.py` (21)
- `test_ast_serialization.py` (40)
- `test_ast_instrument.py` (13)
- `test_dsl_integration.py` (40)
- `test_dsl_parser.py` (47)
- `test_dsl_diagnostics.py` (37)
- `test_store.py` (34)
- `test_datastore.py` (22)
- `test_view.py` (31)
- `test_cli.py` (36)
- `test_strategy_config.py` (38)
- All analyzer tests (~100)

Total: ~498 tests

### Tier 3 — Regression (~580 tests, remainder)

Edge cases, serialization, HTML, interactive, AB tests. Run before release.

## Design

1. Add pytest markers in `pyproject.toml`:

   ```ini
   [tool.pytest.ini_options]
   markers = [
       "tier1: critical path tests (~2s)",
       "tier2: integration tests (~6s)",
       "tier3: regression tests",
   ]
   ```

2. Mark each test file with `@pytest.mark.tier1` (or class-level).

3. Run targets:
   - `pytest -m tier1` — agent日常开发
   - `pytest -m "tier1 or tier2"` — pre-merge
   - `pytest` — full suite (pre-release)

4. Add `AGENTS.md` instruction: "Always run `pytest -m tier1` after edits.
   Run `pytest -m "tier1 or tier2"` before committing."

## Acceptance Criteria

- [ ] `pytest -m tier1` runs in <3 seconds
- [ ] `pytest -m "tier1 or tier2"` runs in <8 seconds
- [ ] Full `pytest` still runs all 1,310+ tests (after 088 pruning)
- [ ] Each test file has exactly one tier marker
- [ ] `pyproject.toml` markers section added
- [ ] `AGENTS.md` documents the tier system

## Related

- `pyproject.toml` — pytest configuration
- Backlog 088 — prerequisite test pruning
