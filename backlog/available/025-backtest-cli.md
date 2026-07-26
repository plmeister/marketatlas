# 025: Backtest CLI

**Status:** pending  
**Priority:** medium

## Description

CLI interface for running backtests from the command line. Wrap `backtest_run.py` logic into a proper CLI with configurable options.

## Acceptance Criteria

- [ ] CLI accepts `--strategy` / `-s` for strategy YAML file path
- [ ] CLI accepts `--symbol` for market symbol (default: `BTC-USD`)
- [ ] CLI accepts `--start` for start date (default: 2 years ago)
- [ ] CLI accepts `--end` for end date (default: today)
- [ ] CLI accepts `--output` / `-o` for HTML output path (default: `/tmp/backtest_result.html`)
- [ ] CLI accepts `--interval` for candle interval (default: `1d`)
- [ ] CLI prints stats to console: trades count, wins, losses, win rate, P&L, max drawdown, profit factor, expectancy
- [ ] Uses `click` or `argparse` (check project conventions)
- [ ] Supports `--help` with usage examples
- [ ] Error handling for invalid dates, missing files, bad symbols

## Technical Notes

- Refactor `backtest_run.py` into reusable functions, then wrap with CLI
- Keep existing `backtest_run.py` behavior as default (no args = current behavior)
- Stats output format: clean table to stdout

## Related

- `backtest_run.py` — current script
- `src/marketatlas/backtesting/backtester.py` — core backtest engine
- `src/marketatlas/visualization/interactive.py` — HTML output
