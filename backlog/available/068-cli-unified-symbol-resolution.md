# 068: CLI Unified Symbol Resolution

**Status:** in-progress  
**Epic:** data  
**Priority:** high

## Description

The CLI bypasses the multi-backend instrument model. `run`/`fetch` take a raw provider symbol (`--symbol BTC-USD`) and construct a bare `YahooProvider()` — the `InstrumentRegistry` (033) is never consulted, `ProviderChain` (002) is never used, and the persistent `DataStore` cache is keyed by raw provider symbol (`BTC-USD.1d.parquet`) rather than the unified canonical name (`BTCUSD`).

The registry already maps canonical → per-provider symbols, and `YahooProvider` already translates canonical → backend internally *when handed a registry* (`yahoo.py:_resolve_symbol`). The only missing piece is CLI wiring.

Join them up: `--symbol` becomes the **unified canonical instrument name** (e.g. `GBPUSD`), resolved through the registry into backend symbols at fetch time, fetched via the provider chain, and cached under the canonical name so multi-backend runs share one cache.

## Goal

- CLI `--symbol` is the canonical instrument name when it exists in the registry; provider-specific symbols are resolved internally per backend.
- `run` and `fetch` fetch through a `ProviderChain` (yahoo → dukascopy fallback).
- `DataStore` keyed by canonical name — cache is backend-agnostic.
- Backward compatible: an unknown symbol warns and passes through raw (current `BTC-USD` behavior preserved).

## Scope

- `cli.py`:
  - Load `InstrumentRegistry` from `instruments.yaml` (default path, overridable).
  - Construct providers with the registry injected: `YahooProvider(registry=...)`, `DukascopyProvider(registry=...)`.
  - Wrap in `ProviderChain` and use it in `run_command` and `fetch_command` (replaces bare `YahooProvider()`).
  - `--symbol` resolved against the registry; no match → `WARNING` to stderr, raw passthrough.
- Providers:
  - Confirm `DukascopyProvider` accepts a registry and translates canonical → backend like `YahooProvider._resolve_symbol`; add the same translation if missing.
  - Confirm both return `MarketData.symbol` = the canonical input symbol (yahoo already does), so the store keys on canonical.
- `DataStore`: unchanged logic — keys follow `symbol.name`, which is now canonical.

## Non-Goals

- Portfolio / multi-instrument backtest execution (069, 070).
- New providers or new registry commands.
- Migrating existing on-disk caches keyed by raw provider symbols (canonical keying applies going forward).

## Acceptance Criteria

- [ ] `run --symbol GBPUSD` fetches yahoo `GBPUSD=X`, caches as `GBPUSD.1d.parquet`
- [ ] Provider chain fallback exercised: yahoo `SymbolNotFoundError` → dukascopy fetch succeeds
- [ ] `fetch` command resolves through the registry the same way
- [ ] Unknown symbol → warning to stderr + raw passthrough (existing behavior, existing CLI tests keep passing)
- [ ] Canonical-keyed store: a dukascopy-served fetch and a yahoo-served fetch of the same canonical share the same cache file
- [ ] Tests: canonical resolution, chain fallback, unknown-symbol warning, provider-level canonical translation (yahoo + dukascopy)

## Technical Notes

- `YahooProvider._resolve_symbol` already implements canonical→backend; the provider only needs the registry passed at construction.
- `InstrumentRegistry.resolve(symbol, provider)` (reverse lookup) exists for tests / diagnostics.
- Keep the existing `run_command` fetch loop (store-first, native, resample fallback) — only the symbol/providers change. Multi-instrument looping lands in 069.

## Related

- Backlog 033 (instrument registry), 032 (dukascopy provider), 002 (provider chain), 066 (persistent data store)
- `src/marketatlas/cli.py`, `src/marketatlas/data/providers/yahoo.py`, `src/marketatlas/data/providers/dukascopy.py`
