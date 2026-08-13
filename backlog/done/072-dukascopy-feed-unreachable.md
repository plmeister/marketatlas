# 072: Move Dukascopy provider to freeserv chart/json3 API

**Status:** done
**Epic:** data
**Priority:** high

## Decision (2026-08-13)

**Dukascopy data source is the freeserv chart/json3 web API — required, not
optional.** The classic bi5 OHLCV feed is unreachable/unverifiable from the dev
host (see findings below), while the JSON API is proven working live. The bi5
D1/W1 implementation from 071 is **superseded** and may be replaced; keep or
drop it as the JSON API rewrite dictates.

## Description

The classic bi5 feed failed to respond from this host:

- `https://n.dukascopy.com/n/{...}_ohlcv_*.bi5` — connection timeouts (`000`)
- `https://datafeed.dukascopy.com/datafeed/{...}_ohlcv_*.bi5` — `404`/`000`/intermittent `503`, even for intraday M1/M5 and old dates
- `https://datafeed.dukascopy.com/datafeed/{...}/BID_candles_min_1.bi5` / `BID_candles_day_1.bi5` (newer API) — timeouts

**Context: the connection is a mobile phone hotspot with poor signal — network
dropouts are frequent (reported by user).** The mixed 404 / timeout / 503
responses are consistent with a flaky, intermittently-dropping connection, not
necessarily a geo-block.

**Key finding (2026-08-13): the Dukascopy web chart JSON API is reachable and
working from this host**, even while the bi5 feed is not. `~/src/opportunity`
fetches 10y of daily FX data through it (`dukascopy_python` v4.0.1):

```
GET https://freeserv.dukascopy.com/2.0/index.php
  ?path=chart/json3&instrument=EUR/USD&interval=1DAY&offer_side=B
  &time_direction=N&last_update=<ms-cursor>&limit=30000&jsonp=<cb>&splits=true&stocks=true
```

- Requires browser-ish `User-Agent` + `Host: freeserv.dukascopy.com` +
  `Referer` headers — without them the API returns `429`.
- Verified live: `1DAY EUR/USD` → 363 rows, `1WEEK EUR/USD` → 61 rows,
  `1DAY AUD/JPY` → 363 rows. Row format `[ms, open, high, low, close, volume]`,
  paginate forward with `last_update` = last row timestamp.
- The 429 without headers explains earlier false alarm; with headers it is
  stable on this flaky connection.

**Implementation target:** this item directs reworking `DukascopyProvider` to
use the freeserv chart/json3 API instead of the classic bi5 feed. The JSON API
covers D1/W1 directly, sidestepping the unverifiable bi5 daily-timestamp
convention that 071's merged implementation relies on.

## Acceptance Criteria

- [x] `DukascopyProvider` fetches from the freeserv chart/json3 API (headers per Technical Notes); intraday M1–H4 and D1/W1 all work through it
- [x] Supersede 071's bi5 D1/W1 path: bi5 code removed or demoted, D1/W1 no longer depends on it
- [x] Treat `HTTPError 503` as transient (currently unhandled — surfaces as a hard error); `URLError` already retried 3× with backoff
- [x] Provider fails gracefully with a clear message when the feed is down, not silent per-instrument drops
- [x] Decide resilience strategy for flaky networks: raise timeout, more retries, longer backoff, or rely on DataStore gap-only fetch (066)

## Implementation summary

- `DukascopyProvider` rewritten on the freeserv chart/json3 web API (`_BASE_URL` =
  `https://freeserv.dukascopy.com/2.0/index.php`), superseding the classic bi5
  OHLCV feed entirely (bi5 struct/zlib/day-file code removed). Forward
  pagination via `last_update` = last row timestamp; boundary row deduped;
  stops at range end; JSONP response parsed by stripping `(...);`.
- Instrument resolution now yields slash-format codes (`EURUSD` → `EUR/USD`,
  registry mapping preferred); bare 6-letter FX canonicals convert, others
  pass through — the json3 API rejects bare codes with `[null]`.
- Timeframe map: M1–H4 + D1/W1 → `1MIN`…`4HOUR`, `1DAY`, `1WEEK` (verified
  live: D1/W1/M5).
- Resilience: `request_timeout` default 60s, `max_retries` default 5 with
  linear backoff; `HTTPError 503` and `URLError` now retried and then raise
  new `FeedUnavailableError` (clear message naming instrument + timeframe);
  `429` → `RateLimitError`; `404` → `NoDataAvailableError`.
- Page-level local cache (`cache_dir/dukascopy/{instrument}/{tf}/{cursor_ms}.json`);
  DataStore gap-only fetch (066) remains the higher-level cache.
- New `FeedUnavailableError` in `providers/base.py`; `ProviderChain` treats it
  as fallback-able (like `RateLimitError`).
- Tests: 20 dukascopy + 12 provider-chain tests (JSONP parse, timestamps,
  all-8-timeframes, pagination cursor advance + dedup, end-stop, 404/429/503/
  URLError retries + success recovery, cache reuse, symbol resolution slash
  default + registry, chain fallback on feed down). 1349 total.

## Technical Notes

- `_BASE_URL` on main is now `https://datafeed.dukascopy.com/datafeed/...` (071); original was `n.dukascopy.com/n/...`. Neither responded in probes.
- On a dropping connection `urllib` raises `URLError` (retried) or `HTTPError 503` (unhandled). Both transient.
- The DataStore gap-only fetch (066) limits network exposure for covered ranges; warm the cache once on a good connection.

## Related

- `src/marketatlas/data/providers/dukascopy.py`
- Backlog 071 — D1/W1 support (merged 2026-08-13 via bi5; superseded by this item)
- Backlog 073 — ProviderChain fallback bug (implemented 2026-08-13)
