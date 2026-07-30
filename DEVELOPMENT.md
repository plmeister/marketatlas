# MarketAtlas

## Prerequisites

- Python 3.11+
- Poetry

## Setup

```bash
poetry install
```

## Run CLI

```bash
poetry run marketatlas --help
poetry run marketatlas fetch --symbol BTC-USD --start 2023-01-01
poetry run marketatlas run -s strategies/pullback_4swing.yaml
```

## Run Tests

```bash
poetry run pytest
poetry run pytest tests/test_swing_structure_analyzer.py -v
```

## Lint & Type Check

```bash
poetry run ruff check src/ tests/
poetry run mypy src/
```

## Backtest

```bash
poetry run python backtest_run.py
```
