# 072: Dukascopy datafeed unreachable from dev host

**Status:** pending
**Epic:** data
**Priority:** high

## Description

Live probes from this host (2026-08-13) failed to reach the Dukascopy classic
bi5 OHLCV datafeed:

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

**Recommendation:** rework `DukascopyProvider` to use the freeserv chart/json3
API instead of the classic bi5 feed (see 071 Technical Notes — it covers
D1/W1 directly, sidestepping the unverifiable bi5 daily-timestamp convention).
A D1/W1 bi5 implementation (071) was merged on 2026-08-13 but remains
unverifiable while the bi5 feed is unreachable; the JSON API is the live,
proven path.

## Acceptance Criteria

- [ ] Decide final data source: freeserv chart/json3 API (proven live) vs classic bi5 feed (071, currently unreachable/unverifiable)
- [ ] If JSON API chosen: wire it into `DukascopyProvider` per 071; keep intraday M1–H4 working
- [ ] Treat `HTTPError 503` as transient (currently unhandled — surfaces as a hard error); `URLError` already retried 3× with backoff
- [ ] Provider fails gracefully with a clear message when the feed is down, not silent per-instrument drops
- [ ] Decide resilience strategy for flaky networks: raise timeout, more retries, longer backoff, or rely on DataStore gap-only fetch (066)

## Technical Notes

- `_BASE_URL` on main is now `https://datafeed.dukascopy.com/datafeed/...` (071); original was `n.dukascopy.com/n/...`. Neither responded in probes.
- On a dropping connection `urllib` raises `URLError` (retried) or `HTTPError 503` (unhandled). Both transient.
- The DataStore gap-only fetch (066) limits network exposure for covered ranges; warm the cache once on a good connection.

## Related

- `src/marketatlas/data/providers/dukascopy.py`
- Backlog 071 — D1/W1 support (implemented via bi5 2026-08-13; verify or replace with JSON API)
- Backlog 073 — ProviderChain fallback bug (implemented 2026-08-13)
