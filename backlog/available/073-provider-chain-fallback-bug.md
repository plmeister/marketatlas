# 073: ProviderChain fallback misses unsupported-timeframe ValueError

**Status:** pending
**Epic:** data
**Priority:** high

## Description

`ProviderChain.fetch` (src/marketatlas/data/providers/chain.py:22) only falls
back to the next provider on `SymbolNotFoundError` / `RateLimitError`. A
`ValueError` raised by a provider for an unsupported timeframe escapes the
chain untouched, so the next provider is never tried.

Observed in the 29-instrument portfolio run (2026-08-13): every forex pair with
`provider_priority: [dukascopy, yahoo]` failed — `DukascopyProvider` raises
`ValueError("Unsupported timeframe: 1d")` for `1d`/`1w`, which bypassed the
Yahoo fallback and surfaced in `fetch_instrument_data` as
"cannot fetch or resample (no source data)". Verified Yahoo serves the same
pairs (`AUDCAD=X` → 23 candles OK). 21/29 instruments dropped as a result.

## Acceptance Criteria

- [ ] `ProviderChain.fetch` falls through to the next provider when the current provider rejects the timeframe as unsupported
- [ ] Unsupported-timeframe handling defined explicitly: either a dedicated exception type (e.g. `UnsupportedTimeframeError`) that the chain treats as fallback-able, or `ValueError` added to the caught set
- [ ] A provider that fails with a hard error (network, auth, rate limit exhausted) still stops the chain with the original exception semantics
- [ ] Unit test: chain with [provider-raising-ValueError, working-provider] returns working provider's data; regression test for the forex portfolio fetch path
- [ ] `DukascopyProvider._timeframe_minutes` raises the agreed fallback-able error (today it raises bare `ValueError`)

## Technical Notes

- Do not blanket-catch `Exception` in the chain — that would swallow hard failures (network/rate-limit) and silently degrade data quality.
- Unsupported timeframe is a *capability* property, not a transient failure; consider querying `provider.supported_timeframes` first if a contract API exists (058 provider contracts are fact-level, not timeframe-level today).
- Related symptom in `fetch_instrument_data` (src/marketatlas/data/portfolio.py:175): the `except ValueError: pass` there hides the real cause. Improve the log to name the provider + timeframe + reason.

## Related

- `src/marketatlas/data/providers/chain.py`
- `src/marketatlas/data/providers/dukascopy.py` (`_timeframe_minutes`, :55)
- `src/marketatlas/data/portfolio.py` (`fetch_instrument_data`, :175)
- Backlog 071, 072 — Dukascopy D1/W1 + feed reachability
