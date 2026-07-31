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

### JavaScript tests

The interactive chart (`src/marketatlas/visualization/base/`) is split into
MVC modules with unit tests run via Node's built-in test runner (no framework
deps):

```bash
node tests/js/models.test.js        # AppModel business logic
node tests/js/views.test.js         # ChartView TF annotations, panels, timeline
node tests/js/controllers.test.js   # Playback, keyboard, TF switching
```

All three at once:

```bash
for f in tests/js/*.test.js; do node "$f"; done
```

Notes:
- `views.test.js` and `controllers.test.js` use the LightweightCharts/DOM
  mocks in `tests/js/mock_helpers.js`; no browser needed.
- Annotation overlays (EMA, zigzag, ATR, S/R) are expected **only on the
  primary timeframe**; trade price lines appear on all timeframes. New
  chart behavior should preserve that split.
- If you refactor shared test data, edit `tests/js/sample_data.js`.

## Lint & Type Check

```bash
poetry run ruff check src/ tests/
poetry run ruff check src/ tests/ --fix   # safe auto-fix, do before agent edits
poetry run ruff format src/ tests/        # format source
poetry run mypy src/
```

## Backtest

```bash
poetry run marketatlas run -s strategies/pullback_4swing.yaml
```
