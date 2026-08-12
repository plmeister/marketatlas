# 069: Portfolio Instrument File & Data Loading

**Status:** done  
**Epic:** portfolio  
**Priority:** high

## Description

Portfolio backtests need a declared instrument list. Today `run` accepts exactly one `--symbol`. The registry (033) holds the universe of known instruments, but there is no way to declare "run this strategy over these N instruments for the same period" and no shared data-loading path that acquires all of them consistently.

A portfolio file defines the list of instruments (by canonical name); `run --instruments file.yaml` loads it, resolves every canonical against the registry, and fetches/loads data for all of them over the identical start/end range — ready for the portfolio execution engine (070).

## Goal

- Portfolio file format: YAML `instruments:` list of canonical names.
- `run` accepts `--instruments <file>`; resolves each canonical, errors clearly on unknowns.
- One shared data-loading path fetches all instruments over the same period, reusing the existing single-symbol fetch/resample/store logic from `run_command`.
- Data cached per canonical (from 068) so repeated runs hit the store.

## Scope

- **File format** (`docs`-style spec in this backlog):
  ```yaml
  instruments:
    - GBPUSD
    - BTCUSD
    - EURUSD
  ```
  Canonical names only — provider symbols are a registry concern (068). No per-instrument timeframe/weight overrides in v1 (non-goal).
- **Loader**: `PortfolioSpec` (or `load_portfolio(path, registry) -> tuple[Instrument, ...]`):
  - Parses the YAML list; empty list → error.
  - Resolves each canonical via `InstrumentRegistry.get`; missing → error naming the instrument and its index.
  - Dedupes; keeps file order.
- **`--instruments` flag** on `run`, mutually aware with `--symbol`:
  - `--instruments` present → portfolio path (ignore `--symbol`).
  - absent → current single-symbol path unchanged (portfolio of one).
- **Data acquisition**: extract the fetch block from `run_command` (store-first → native → resample, per-timeframe) into a reusable helper, e.g. `fetch_instrument_data(provider_chain, datastore, instrument, timeframes, start, end, base_tf) -> dict[Timeframe, MarketData]`. The portfolio path calls it once per instrument with identical `start`/`end`.
  - Keep `fetch_command` as-is (068 already unified its symbols).
- **Validation before fetch**: a strategy requiring TFs that fail fetch/resample for one instrument aborts that instrument with a clear error, not a silent partial run.

## Non-Goals

- The portfolio execution engine / shared tradebook (070).
- Per-instrument parameters (timeframe, weights, risk) in the portfolio file.
- Cross-instrument data features (group nodes already exist per 064 — out of scope here).

## Acceptance Criteria

- [ ] `--instruments portfolio.yaml` with 2+ canonicals loads data for all, identical start/end
- [ ] Missing canonical → error naming the instrument (e.g. `Unknown instrument 'XXX' at index 2 in portfolio file`)
- [ ] Empty/malformed portfolio file → clear error
- [ ] Duplicate canonicals deduped, order preserved
- [ ] Single-`--symbol` run path unchanged (existing CLI tests pass)
- [ ] Per-canonical caching: second run served from store (extend `test_run_second_run_served_from_store` to the portfolio path)
- [ ] Instrument-level fetch failure reported with instrument context
- [ ] Tests: file parsing, validation, multi-instrument fetch (incl. resample fallback per instrument), store reuse

## Technical Notes

- `MarketStore` is single-symbol (multi-timeframe); the portfolio keeps one `MarketStore` per instrument. Container decision is 070's (per-instrument `(Instrument, MarketStore)` pairs match `backtest_template`'s input shape from 063).
- `DataRequirement`/`required_data` (065) cover the AST/DSL path; the YAML-strategy path (016) has no `TemplateGraph`, so the per-instrument fetch helper covers it. Unify later if the DSL path needs the same CLI portfolio loading.
- Reuse the existing store-first/resample logic verbatim — extraction only, no behavior change.

## Related

- Backlog 068 (canonical symbol + provider chain + canonical-keyed store), 033 (registry), 046 (multi-timeframe fetching), 065 (data requirements), 063 (per-instrument result shape)
- `src/marketatlas/cli.py` (`run_command` fetch block), `src/marketatlas/data/instrument.py`
