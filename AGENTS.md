# AGENTS.md

## How to run the project

ALWAYS use Poetry for this project — never `uv`.

```sh
poetry run marketatlas ...     # run the CLI
poetry run pytest ...          # run tests
poetry run python ...          # run a script
```

Why:
- Project is Poetry-managed (`[tool.poetry]` in `pyproject.toml`, `poetry.lock`).
- `uv run` emits a spurious `requires-python` warning and can drop a stray
  `uv.lock` into the repo. It is not the project's dependency manager.

Do not add `uv.lock` to the repo. If a stray `uv.lock` appears, remove it.

## Tests & lint

```sh
poetry run pytest -m tier1                     # critical path (~2s) — after every edit
poetry run pytest -m "tier1 or tier2"          # integration (~6s) — before commit
poetry run pytest                              # full Python suite (~16s) — before release
npm test                                       # JS visualization suite
npm run lint                                   # JS lint (pre-existing no-undef in crosshair.js)
poetry run ruff check src/                     # Python lint
poetry run mypy src/marketatlas/               # Python type check
```

Tiers (from `pyproject.toml`): `tier1` critical path, `tier2` integration,
`tier3` regression.

## Module map

```
analysis/analyzers/    — compute facts from candle data (EMA, ATR, trend, S/R, swings)
analysis/ast/          — DSL compiler: lex → parse → expand → validate → compile
analysis/patterns/     — pattern detection (pullback)
analysis/signals/      — trade signal evaluation (pullback signal)
backtesting/           — single-instrument and portfolio backtest runners
data/                  — market data providers, store, portfolio, instrument models
evidence/              — evidence entry model and collector
facts/                 — immutable fact types (EMA, ATR, trend, swing, pullback)
frames/                — analysis frame storage and parquet I/O
strategy/              — risk engine, trade lifecycle, signal/strategy config
visualization/         — HTML chart builder, interactive renderer, portfolio output
```

## Data flow

```
MarketStore → MarketView → AnalysisGraph.run(view) → {FactKey: Fact}
     ↓                                                    ↓
     ↓                                            Strategy.evaluate(view, facts)
     ↓                                                    ↓
     ↓                                            [TradeSignal, ...]
     ↓                                                    ↓
     ↓                                            RiskEngine.evaluate(signal, facts)
     ↓                                                    ↓
     ↓                                            TradeCandidate | None
     ↓                                                    ↓
     ↓                                            TradeBook.submit_order / fill_order
     ↓                                                    ↓
     ↓                                            AnalysisFrame (evidence + signals + risk)
     ↓                                                    ↓
     └────────────────────────────────────────→ Visualization (HTML chart)
```

## Key abstractions

| Type | Location | Purpose |
|------|----------|---------|
| `Fact` | `facts/base.py` | Immutable analysis result with evidence |
| `FactKey` | `analysis/factkey.py` | Named+timeframe key for fact lookup |
| `Analyzer` | `analysis/base.py` | Computes facts from view + prior facts |
| `AnalysisGraph` | `analysis/graph.py` | DAG of analyzers, topological execution |
| `Signal` | `strategy/signals.py` | Evaluates facts → TradeSignal or rejection |
| `TradeCandidate` | `strategy/trade.py` | Sized trade with entry/stop/target |
| `TradeBook` | `strategy/tradebook.py` | Trade lifecycle: submit → fill → resolve |
| `RiskEngine` | `strategy/risk.py` | Signal → candidate sizing + validation |

## Task recipes

### Add a new analyzer

1. Create `analysis/analyzers/my_analyzer.py` extending `Analyzer`
2. Implement `requires()`, `produces()`, `analyze()`
3. Register in `analysis/ast/registry.py` (provider + contract)
4. Add DSL grammar entry in `analysis/ast/constructors.py`
5. Test: create fact fixture, verify output in `tests/test_analysis.py`

### Add a new signal type

1. Create `analysis/signals/my_signal.py` extending `Signal`
2. Implement `evaluate(view, facts) -> TradeSignal | None`
3. Register in `strategy/strategy.py` signal map (or use registry from backlog 087)
4. Test: create fact fixtures, verify signal output in `tests/test_signal_system.py`

### Add a new risk filter

1. Add condition to `strategy/risk.py` `evaluate()` method
2. Add rejection evidence (use existing `EvidenceEntry` pattern)
3. Test in `tests/test_risk_engine.py`

### Modify chart annotations

1. Edit `visualization/base/views.js` → `_hitAnnotationTooltip()`
2. Data comes from `AnalysisFrame.evidence` / `.signal_rejections`
3. Test: `npm test` (JS tests in `tests/js/`)
