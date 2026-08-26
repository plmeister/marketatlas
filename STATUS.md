# Status

## MVP Progress

- [x] 001 — Project scaffolding
- [x] 006 — Fact type system
- [x] 003 — Parquet data loading
- [x] 004 — MarketStore
- [x] 005 — MarketView
- [x] 007 — Analyzer interface + graph
- [x] 008 — EMA analyzer
- [x] 009 — ATR analyzer
- [x] 010 — Trend analyzer
- [x] 011 — Pullback detector
- [x] 012 — Analysis frame storage
- [x] 013 — Evidence model
- [x] 014 — Backtesting replay loop
- [x] 015 — HTML visualization
- [x] 002 — External data fetcher
- [x] 066 — Persistent data store

## Data Layer

- [x] 032 — Dukascopy provider (classic bi5 feed)
- [x] 071 — Dukascopy D1/W1 via bi5 (superseded by 072)
- [x] 072 — Dukascopy moved to freeserv chart/json3 API (bi5 gone; `FeedUnavailableError` for feed-down, `ProviderChain` fallback)
- [x] 092 — Data provider plugin system (`providers/registry.py` with register/get, providers self-register on import, `cli._make_provider` falls back to registry for unknown providers)

## Strategy Layer

- [x] 016 — Strategy config loader (YAML)
- [x] 017 — Swing structure analyzer
- [x] 018 — Four-swing pullback detector
- [x] 019 — Support/resistance analyzer
- [x] 020 — Signal system
- [x] 021 — Risk layer & trade sizing
- [x] 022 — Strategy-aware backtester
- [x] 023 — No-read-ahead audit
- [x] 024 — Interactive strategy visualization
- [x] 025 — Backtest CLI
- [x] 034 — Frame stepper candle visibility
- [x] 035 — Future candle visibility
- [x] 033 — Instrument registry
- [x] 046 — Multi-timeframe data fetching
- [x] 045 — Multi-resolution MarketView
- [x] 067 — Confirmed pullback entry (entry-day gating, confirmation candle, rejection evidence)

> **Architecture note (067):** `AnalysisGraph.run_with_evidence()` (replaces `run()` internally) also returns analyzer evidence from frames that produced no fact; `Backtester` threads this loose evidence onto the frame so gated/rejected patterns are observable in backtests.
- [x] 068 — CLI unified symbol resolution (`--symbol` canonical, per-instrument provider priority chain, canonical-keyed DataStore; unknown symbol → WARNING passthrough)
- [x] 087 — Signal registry (decoupled signal registration from Strategy class via `analysis/signals/registry.py` `SIGNAL_TYPES` dict; AST registry derives from same source)

## Portfolio Layer

- [x] 069 — Portfolio instrument file & data loading (`PortfolioSpec`/`load_portfolio`, shared `fetch_instrument_data` helper, `run --instruments <file>` loads all instruments over identical start/end into the canonical-keyed store, per-instrument abort with context)
- [x] 075 — PortfolioBacktester core (merged primary-timeframe calendar, shared TradeBook, per-instrument frame alignment, deterministic entry order, `BundleProtocol.strategies`, `PortfolioBacktestResult.by_instrument`)
- [x] 077 — Portfolio visualization (`render_portfolio`/`render_portfolio_index` in `visualization/portfolio.py`: per-instrument charts reuse `InteractiveRenderer` with `TradeBook.filtered_by_instrument`, lightweight static index page `{stem}.html` with shared-book summary + per-instrument rows linking to `{stem}.{canonical}.html`; `TradeBook` by-instrument/by-strategy breakdowns extended with `trades`/`win_rate`/`profit_factor` consumed from `summary` directly)
- [x] 079 — Portfolio A/B test runner (`run --ab --instruments` expands choice templates and runs one `PortfolioBacktester` per variant on a fresh `StrategyBundle`/`TradeBook`; `analysis/ast/variant.py` derives variant identity/labels across every node type — analyzer params, signal rules, risk params; shared `_load_ab_stores` fetch/store helper for both `--ab` paths; `.dsl` required under `--ab`)
- [x] 080 — A/B output tree (`variant_slugs` derives deterministic ordinal-free slugs from the same variant-identity logic as the 079 labels — `min_strength=0.5` → `ms050`; shared `_render_ab_variants` writes `--output out.html` → `out/<slug>/out.html` per single-symbol variant and `out/<slug>/portfolio.<canonical>.html` per instrument on the portfolio path)
- [x] 081 — A/B comparison index (`render_ab_index` in `visualization/portfolio.py`: static `ab.html` at the output-tree root — summary grid one row per choice combination (columns = varying choice dims + Trades/W-L/Win rate/P&L/Return/Max DD/PF/Expectancy from `TradeBook.summary`, no recompute) + per-variant by-instrument/by-strategy tables reusing the 077 `_sign_class`/`_fmt_*` markup, each instrument row linking to its 080 chart via relative href; `variant_columns` derives grid headers/slugs from variant identities alone, shared with the 079/080 label/slug logic)
- [x] 082 — A/B index page controls (`render_ab_index` progressive enhancement: one `<select>` per choice dimension in a `#ab-controls` bar; variant data embedded once as `AB_VARIANTS`/`AB_DIMS` JSON built from the same `TradeBook.summary` the 081 tables use, re-rendered by a single inline dependency-free `_AB_INDEX_JS` block (JSON-driven `#ab-grid-body` rows with `_fmt_*`-identical formatting + `data-slug`-keyed show/hide of `section.variant` details, `#ab-count` readout); default "All" state identical to the 081 page and full static tables survive JS-disabled, so JSON is purely additive)
- [x] 094 — Parallel instrument analysis (`ThreadPoolExecutor` for per-instrument `graph.run_with_evidence` + `evaluate_all_with_rejections` in `PortfolioBacktester` inner loop; module-level `_analyze_instrument` for pickling; configurable `pool_size` param, defaults to `min(instruments, cpu_count)`; single-instrument path unchanged)

## AST Layer

- [x] 036 — AST model (core node types)
- [x] 037 — Builder API (fluent construction)
- [x] 038 — AST validation (semantic checks)
- [x] 039 — AST serialization (JSON)
- [x] 040 — Compiler adapter (AST to graph)
- [x] 041 — Capability, Provider, Definition separation
- [x] 047 — Expression hierarchy (Parameter.value → Expression)
- [x] 048 — ChoiceExpression node (template expansion point)
- [x] 050 — Template expansion pass (ChoiceExpression → concrete ASTs)
- [x] 051 — Compiler pipeline stages (4-stage: validation → expansion → concrete validation → graph)
- [x] 052 — Provider param schema validation (registry-derived, post-resolution, per-leaf Choice type checks)
- [x] 053 — Provider construction API (`EMA(period=20)` factories + `build_analysis` composition)
- [x] 054 — Compiler golden tests (choice expansion, inline expected outputs)
- [x] 055 — DSL grammar specification (docs/dsl.md: EBNF, semantics, design decisions, pipeline mapping)
- [x] 056 — DSL lexer (token stream + positioned SourcePosition, DslSyntaxError)
- [x] 057 — DSL parser (template AST from text, reference/shorthand bindings)
- [x] 058 — Provider contract metadata (inputs/outputs per provider, registry-held)
- [x] 059 — Positioned diagnostics (Diagnostic.position, SourceMap, line:col formatter + caret snippet)
- [x] 061 — Timeframe declaration on analysis nodes (Definition.timeframe, Analysis.timeframes, DSL `timeframe` field)
- [x] 062 — Cross-timeframe references (analyzer `bindings` overrides from references, FactKey `@tf` keys, signal requires carries source TF, output-vs-contract validation)
- [x] 063 — Instrument runtime expansion (TemplateGraph recipe, per-instrument instantiation, isolated multi-instrument backtests)
- [x] 064 — Market groups: cross-instrument nodes (group-scoped definitions, spanning `*` references, GroupGraph instantiation)
- [x] 065 — Data requirements inference (required_timeframes/required_data, DataRequirement, gap-only fetching via DataStore)
- [x] 084a — Signal/Risk requires(): Signal ABC declares abstract requires(), PullbackSignal implements (pullback_pattern, trend, atr_14), RiskEngine implements (atr_14, sr, swing)
- [x] 084b — Signal/risk contracts: `_derive_contract` already handles requires()/produces() from signals and risk; acceptance criteria tests added
- [x] 084c — Compiler completeness check: CompletenessPass verifies every contract-declared analyzer input supplied as ReferenceExpression param; CompilationError frozen dataclass fix; tests updated for complete DSL bindings
- [x] 084d — TrendAnalyzer requires atr_14: `requires()` includes `FactKey("atr_14")`, removed optional ATR fallback (hard error if missing), updated `swing.dsl` trend node with `atr_14: atr_14`, all test DSL strings and builder API tests updated
- [x] 084e — PullbackSignal DSL-injected keys: constructor gains `bindings: dict[str, str] | None = None` param (follows RiskEngine pattern); `evaluate()` resolves keys via `self._bindings.get("pullback_pattern", self._pullback_key)` etc.; compiler-injected keys from `SignalConfig.rules["bindings"]` now consumed instead of ignored; programmatic construction defaults unchanged
- [x] 085 — Split pipeline.py → expansion.py + lowering.py + pipeline.py (thin orchestrator)