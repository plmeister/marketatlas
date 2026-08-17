# 090: Add AGENTS.md with architecture guide and task recipes

**Status:** pending
**Epic:** docs
**Priority:** high
**Depends on:** none

## Description

Agents exploring this codebase have no navigation guide. They must
grep/glob/read dozens of files to understand data flow, abstractions, and
where to make changes. An `AGENTS.md` at repo root provides a single entry
point.

## Content

### Module Map (one-liner per directory)

```
analysis/analyzers/   — compute facts from candle data (EMA, ATR, trend, S/R, swings)
analysis/ast/         — DSL compiler: lex → parse → expand → validate → compile
analysis/patterns/    — pattern detection (pullback)
analysis/signals/     — trade signal evaluation (pullback signal)
backtesting/          — single-instrument and portfolio backtest runners
data/                 — market data providers, store, portfolio, instrument models
evidence/             — evidence entry model and collector
facts/                — immutable fact types (EMA, ATR, trend, swing, pullback)
frames/               — analysis frame storage and parquet I/O
strategy/             — risk engine, trade lifecycle, signal/strategy config
visualization/        — HTML chart builder, interactive renderer, portfolio output
```

### Data Flow

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

### Key Abstractions

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

### Task Recipes

**Add a new analyzer:**
1. Create `analysis/analyzers/my_analyzer.py` extending `Analyzer`
2. Implement `requires()`, `produces()`, `analyze()`
3. Register in `analysis/ast/registry.py` (provider + contract)
4. Add DSL grammar entry in `analysis/ast/constructors.py`
5. Test: create fact fixture, verify output in `tests/test_analysis.py`

**Add a new signal type:**
1. Create `analysis/signals/my_signal.py` extending `Signal`
2. Implement `evaluate(view, facts) -> TradeSignal | None`
3. Register in `strategy/strategy.py` signal map (or backlog 087 registry)
4. Test: create fact fixtures, verify signal output in `tests/test_signal_system.py`

**Add a new risk filter:**
1. Add condition to `strategy/risk.py` `evaluate()` method
2. Add rejection evidence (use existing `EvidenceEntry` pattern)
3. Test in `tests/test_risk_engine.py`

**Modify chart annotations:**
1. Edit `visualization/base/views.js` → `_hitAnnotationTooltip()`
2. Data comes from `AnalysisFrame.evidence` / `.signal_rejections`
3. Test: `npm test` (JS tests in `tests/js/`)

**Run tests:**
- `pytest -m tier1` — critical path (~2s), run after every edit
- `pytest -m "tier1 or tier2"` — integration (~6s), run before commit
- `pytest` — full suite (~16s), run before release
- `npm test` — JS visualization tests
- `ruff check src/` — lint
- `mypy src/marketatlas/` — type check

## Acceptance Criteria

- [ ] `AGENTS.md` exists at repo root
- [ ] Contains: module map, data flow diagram, key abstractions table, task recipes
- [ ] Task recipes cover: add analyzer, add signal, add risk filter, modify chart, run tests
- [ ] Recipes reference specific files and line numbers
- [ ] No duplicate information with `DEVELOPMENT.md` or `ARCHITECTURE-ROADMAP.md`

## Related

- `DEVELOPMENT.md` — existing dev docs (workflow, not architecture)
- `ARCHITECTURE-ROADMAP.md` — existing roadmap (planning, not navigation)
