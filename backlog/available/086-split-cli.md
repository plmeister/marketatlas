# 086: Split cli.py into command handlers

**Status:** pending
**Epic:** cli
**Priority:** medium
**Depends on:** none

## Description

`cli.py` is 870 lines — the second-largest Python file. It mixes argument
parsing, command orchestration, output formatting, and error handling for
fetch, run, run-portfolio, and ab-test commands in one monolith.

Split into:

- **`cli/commands.py`** (~500 lines) — individual command handler functions:
  `cmd_fetch`, `cmd_run`, `cmd_run_portfolio`, `cmd_ab`. Each receives parsed
  args and returns a result; no `sys.exit` calls inside handlers.
- **`cli/formatting.py`** (~150 lines) — output formatting helpers:
  summary table rendering, progress callbacks, JSON/text output selection.
- **`cli/errors.py`** (~50 lines) — error classes and the `exit_code` mapping
  (currently inlined in `cli.py`).
- **`cli.py`** (~170 lines) — thin entry point: argparse setup, subcommand
  dispatch, top-level exception→exit-code handler.

## Design

1. `cli.py` remains the `__main__` entry point. It imports from
   `cli/commands.py` and dispatches.
2. Each `cmd_*` function takes `(args, config_path)` and returns a dataclass
   result; `cli.py` catches exceptions and maps to exit codes.
3. `formatting.py` contains `format_summary`, `format_trades`,
   `progress_callback` — pure functions, no CLI imports.
4. `errors.py` defines `CLIError`, `ConfigError`, `FetchError` and the
   `EXIT_*` constants.
5. `pyproject.toml` scripts unchanged (`marketatlas = "marketatlas.cli:main"`).

## Acceptance Criteria

- [ ] `cli.py` <200 lines, no command logic inline
- [ ] `cli/commands.py` <550 lines, each `cmd_*` function <150 lines
- [ ] `cli/formatting.py` <200 lines, pure functions (no sys/os imports)
- [ ] `pytest tests/test_cli.py` — all 36 tests pass unchanged
- [ ] `ruff check` clean, `mypy` clean
- [ ] `marketatlas run --help` still works

## Related

- `src/marketatlas/cli.py` (870 lines, primary target)
- `tests/test_cli.py` (1,770 lines, 36 tests — largest test file)
