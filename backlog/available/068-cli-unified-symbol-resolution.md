# 068: CLI Unified Symbol Resolution

**Status:** in-progress  
**Epic:** data  
**Priority:** high

## Description

The CLI bypasses the multi-backend instrument model. `run`/`fetch` take a raw provider symbol (`--symbol BTC-USD`) and construct a bare `YahooProvider()` — the `InstrumentRegistry` (033) is never consulted, `ProviderChain` (002) is never used, and the persistent `DataStore` cache is keyed by raw provider symbol (`BTC-USD.1d.parquet`) rather than the unified canonical name (`BTCUSD`).

The registry already maps canonical → per-provider symbols, and `YahooProvider` already translates canonical → backend internally *when handed a registry* (`yahoo.py:_resolve_symbol`). The only missing piece is CLI wiring.

Two gaps to close:

1. **Symbol join-up**: `--symbol` should be the **unified canonical instrument name** (e.g. `GBPUSD`), resolved through the registry into backend symbols at fetch time, fetched via the provider chain, and cached under the canonical name so multi-backend runs share one cache.
2. **Provider priority**: the chain has a single hard-coded order (yahoo first). Instruments differ — yahoo candles are suspect for FOREX, dukascopy has no D1/W1 native. Each instrument needs to **specify its preferred providers, or a priority-ordered list**, so the chain tries them per-instrument.

## Goal

- CLI `--symbol` is the canonical instrument name when it exists in the registry; provider-specific symbols are resolved internally per backend.
- `run` and `fetch` fetch through a `ProviderChain` ordered **per instrument** by the instrument's declared provider priority.
- `DataStore` keyed by canonical name — cache is backend-agnostic.
- Backward compatible: an unknown symbol warns and passes through raw (current `BTC-USD` behavior preserved); no priority declared → current default order.

## Scope

- **Registry — provider priority** (`data/instrument.py`):
  - `Instrument` gains `provider_priority: tuple[str, ...]` (optional). Explicit, ordered; provider dict insertion order is *not* used as priority (fragile).
  - YAML form: `provider_priority: [dukascopy, yahoo]` under the instrument (or `providers` dict order honored if no explicit list — decide; prefer explicit list only, dict order ignored).
  - `from_dict`/`to_dict`/`__eq__`/`save` round-trip it. Unknown provider name in the list → validated against registered provider names (registry or cli-level), error on unknown.
  - `InstrumentRegistry.get_priority(canonical) -> tuple[str, ...]` returns the declared order or the default.
  - `instruments add` gains `--provider-priority` flag (comma-separated, optional).
- `cli.py`:
  - Load `InstrumentRegistry` from `data/instruments.yaml` (default path, overridable).
  - Construct providers with the registry injected: `YahooProvider(registry=...)`, `DukascopyProvider(registry=...)`.
  - Build a `ProviderChain` **per instrument** whose provider order = that instrument's `provider_priority` (default order otherwise). Use it in `run_command` and `fetch_command` (replaces bare `YahooProvider()`).
  - `--symbol` resolved against the registry; no match → `WARNING` to stderr, raw passthrough (default chain).
- Providers:
  - Confirm `DukascopyProvider` accepts a registry and translates canonical → backend like `YahooProvider._resolve_symbol` (it already has `_resolve_symbol`, 032); both return `MarketData.symbol` = the canonical input symbol (yahoo does), so the store keys on canonical.
- `DataStore`: unchanged logic — keys follow `symbol.name`, which is now canonical.

## Non-Goals

- Portfolio / multi-instrument backtest execution (069, 070).
- New providers (only reordering existing yahoo/dukascopy).
- Class-based defaults (FOREX→dukascopy) — per-instrument priority only; a shared default can be encoded in the registry file.
- Migrating existing on-disk caches keyed by raw provider symbols (canonical keying applies going forward).

## Acceptance Criteria

- [ ] `run --symbol GBPUSD` with `provider_priority: [dukascopy]` fetches dukascopy, caches as `GBPUSD.1d.parquet`
- [ ] Provider chain fallback exercised: priority-1 provider `SymbolNotFoundError` → priority-2 provider fetch succeeds
- [ ] `fetch` command resolves through the registry and priority the same way
- [ ] No priority declared → default chain order (current behavior), unknown symbol → warning + raw passthrough (existing CLI tests keep passing)
- [ ] Registry round-trips `provider_priority` (YAML load/save); unknown priority provider → clear error
- [ ] Canonical-keyed store: dukascopy-served and yahoo-served fetches of the same canonical share one cache file
- [ ] Tests: priority parsing/round-trip/validation, per-instrument chain ordering, chain fallback, unknown-symbol warning, provider-level canonical translation (yahoo + dukascopy)

## Technical Notes

- `YahooProvider._resolve_symbol` / `DukascopyProvider._resolve_symbol` already implement canonical→backend; each provider only needs the registry passed at construction.
- `ProviderChain.fetch` already has priority semantics — it catches `SymbolNotFoundError`/`RateLimitError` and tries the next provider (`chain.py`). Per-instrument priority only changes *which providers, in what order* the chain wraps; the chain itself stays dumb.
- Dukascopy native TFs are M1–H4 (`dukascopy.py:_TIMEFRAME_MINUTES`); daily/weekly FOREX still falls back to resample-from-H1/H4 via the existing `run_command` resample loop (046) or yahoo-native D1/W1 when priority allows.
- `InstrumentRegistry.resolve(symbol, provider)` (reverse lookup) exists for tests / diagnostics.
- Keep the existing `run_command` fetch loop (store-first, native, resample fallback) — only the symbol/providers change. Multi-instrument looping lands in 069.

## Related

- Backlog 033 (instrument registry), 032 (dukascopy provider), 002 (provider chain), 066 (persistent data store), 046 (resample/MTF)
- `src/marketatlas/cli.py`, `src/marketatlas/data/instrument.py`, `src/marketatlas/data/providers/yahoo.py`, `src/marketatlas/data/providers/dukascopy.py`, `src/marketatlas/data/providers/chain.py`
