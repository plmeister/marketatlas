# 071: Dukascopy D1/W1 support (daily & weekly candles)

**Status:** done
**Epic:** data
**Priority:** high

## Description

`DukascopyProvider` only maps intraday timeframes M1–H4 in
`_TIMEFRAME_MINUTES` (src/marketatlas/data/providers/dukascopy.py:23). Any
`1d`/`1w` request raises `ValueError("Unsupported timeframe: ...")`, so in a
portfolio run the Dukascopy-first forex pairs (AUDCAD, EURUSD, …) can never
acquire their primary `1d` series — all 21 FOREX instruments were dropped from
the 29-instrument run on 2026-08-13.

The Dukascopy datafeed does serve daily and weekly OHLCV bars (classic
`_ohlcv_{period}.bi5` endpoints use period `1440` for 1d and `10080` for 1w;
newer `BID_candles_day_1.bi5` API also exists). D1/W1 therefore only needs to
be wired into the provider, not invented.

## Acceptance Criteria

- [x] `DukascopyProvider.fetch` returns daily bars for `Timeframe.D1` and weekly bars for `Timeframe.W1` for a forex instrument (unit-tested with mocked bi5 files)
- [x] Daily candle timestamps correct — convention is `probe_day 00:00 UTC + file sec_offset`; live off-by-one/session-close verification still blocked on 072
- [x] Weekly bars iterate by week — new week-granular loop probes one day per week (scans Mon–Sun until a probe returns data; clamped to range end); day-granular loop untouched for intraday/D1
- [x] Unit tests with mocked daily/weekly bi5 files, consistent with existing `test_dukascopy_provider` style
- [ ] Verified live against the datafeed for ≥1 pair (see 072 — feed must be reachable first; unverifiable from this host)
- [x] `_parse_bi5` handles the daily/weekly record layout — classic `_ohlcv_` layout (`>Ifffff`, open/high/low/close) reused unchanged; the newer `BID_candles_*` layout (open/close/low/high, integer prices × point value, 4-byte float volume, one file per year for daily) was cross-checked against theorycraft-trading/dukascopy and deliberately NOT adopted (point-value scaling per instrument)

## Technical Notes

- `_TIMEFRAME_MINUTES` add `Timeframe.D1: 1440`, `Timeframe.W1: 10080` — the day-granular fetch loop got a parallel week-granular path for W1.
- `_parse_bi5` computes `ts = date_start + sec_offset`; daily file yields one candle, weekly one per week. Implemented convention: daily = probe day midnight, weekly = week-start-probe day midnight (or first data-serving day of the week when the start of week 404s). Live confirmation pending 072.
- Cross-check URL patterns against dukascopy-node / theorycraft-trading/dukascopy (`BID_candles_day_1.bi5`, month 0-indexed) and classic `_ohlcv_1440.bi5`.
- Do not rely on this to unblock the portfolio run on its own: even with D1/W1 wired, the feed is unreachable from this host (072) and ProviderChain fallback is broken (073).

## Related

- `src/marketatlas/data/providers/dukascopy.py`
- Backlog 032 (done) — original Dukascopy provider, intraday only
- Backlog 072 — datafeed unreachable from host
- Backlog 073 — ProviderChain fallback misses unsupported-timeframe ValueError
