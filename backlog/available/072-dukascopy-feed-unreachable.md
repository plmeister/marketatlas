# 072: Dukascopy datafeed unreachable from dev host

**Status:** pending
**Epic:** data
**Priority:** high

## Description

Live probes from this host (2026-08-13) cannot reach the Dukascopy datafeed:

- `https://n.dukascopy.com/n/{...}_ohlcv_*.bi5` — always connection timeout (`000`)
- `https://datafeed.dukascopy.com/datafeed/{...}_ohlcv_*.bi5` — `404`/`000`/intermittent `503`, even for intraday M1/M5 and old dates
- `https://datafeed.dukascopy.com/datafeed/{...}/BID_candles_min_1.bi5` / `BID_candles_day_1.bi5` (newer API) — timeouts

Meanwhile `YahooProvider` works normally (fetched `AUDCAD=X` fine), so this is
not a general network failure. Suspect IP geo-blocking or datafeed-side
throttling/blacklisting of this host, or the classic `_ohlcv_` URL scheme being
deprecated server-side.

Consequence: `DukascopyProvider` is effectively dead from this machine today.
Every Dukascopy-priority instrument fails at fetch time, and with ProviderChain
fallback broken (073) the provider never degrades to Yahoo.

## Acceptance Criteria

- [ ] Determine root cause: geo-block vs rate-limit vs deprecated URL scheme (test from another network/VPN, different hostnames, both URL schemes)
- [ ] Confirm current reachable endpoint + URL format (classic `_ohlcv_` vs `BID_candles_*`), and whether `datafeed` vs `n.dukascopy.com` differ
- [ ] Document findings in this backlog; if blocked, decide strategy: add user-agent/headers, switch endpoint, drop Dukascopy, or mark provider unhealthy at runtime
- [ ] Provider should fail gracefully with a clear message when the feed is down, not silent per-instrument drops

## Technical Notes

- `_BASE_URL` currently `https://n.dukascopy.com/n/...` — try `https://datafeed.dukascopy.com/datafeed/...` too.
- Browser-style `User-Agent` made no difference in probes; consider an HTTP debugger (e.g. `curl -v`, Wireshark) to see where the connection dies.
- Check whether a corporate firewall/proxy or geo allowlist blocks `dukascopy.com` from this machine.

## Related

- `src/marketatlas/data/providers/dukascopy.py`
- Backlog 071 — D1/W1 support (blocked on feed reachability)
- Backlog 073 — ProviderChain fallback bug
