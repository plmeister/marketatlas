"""Rebuild the k=3.5 mean-reversion candidate on the refetched history.

Verification target (WORKLOG 2026-10-06, recorded before the /tmp wipe):
- full 2003-2026: n=1318, E[R] +1.374 +/-0.057, win 85.1% at 1.5/3.0, 15 bars
- clean full restricted to 5y window: ~303 trades, ~+2.1R

Signal (stage-14 simplification): alternating fractal(2,2) pivots, leg between
consecutive pivots >= k * SMA-ATR (pivot bar), close confirmation ci=i+2,
entry at signal close, one position per instrument, shorts gated on w_pos.

Run: poetry run python study/signal_check.py
"""

from __future__ import annotations

import statistics
from datetime import timedelta

from data_loader import load, sma_atr

K = 3.5
STOP, TARGET, HORIZON = 1.5, 3.0, 15
SYMBOLS = [
    "AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADJPY",
    "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD",
    "GBPAUD", "GBPJPY", "GBPNZD", "GBPUSD",
    "NZDCAD", "NZDJPY", "NZDUSD", "USDCAD", "USDCHF",
    "XAGUSD", "XAUUSD",
]


def pivots(h: list[float], l: list[float]) -> list[tuple[int, str, float]]:
    """Raw strict fractal(2,2) pivots: [i-2..i+2], self is the extreme."""
    out = []
    n = len(h)
    for i in range(2, n - 2):
        win_h = h[i - 2:i + 3]
        win_l = l[i - 2:i + 3]
        if h[i] == max(win_h) and h[i] > max(h[i - 2:i]) and h[i] > max(h[i + 1:i + 3]):
            out.append((i, "H", h[i]))
        if l[i] == min(win_l) and l[i] < min(l[i - 2:i]) and l[i] < min(l[i + 1:i + 3]):
            out.append((i, "L", l[i]))
    return out


def legs(
    raw: list[tuple[int, str, float]], atr: list[float]
) -> list[tuple[int, str, float]]:
    """Alternating legs: same-type pivots collapse to the extreme, opposite
    pivots are accepted only when travel >= k * ATR (else folded/dropped)."""
    out: list[tuple[int, str, float]] = []
    for i, typ, price in raw:
        if not out:
            out.append((i, typ, price))
            continue
        pi, ptyp, pprice = out[-1]
        if typ == ptyp:
            if (typ == "H" and price > pprice) or (typ == "L" and price < pprice):
                out[-1] = (i, typ, price)
            continue
        ref = atr[i] if atr[i] > 0 else 0.0
        if ref > 0 and abs(price - pprice) >= K * ref:
            out.append((i, typ, price))
    return out


def weekly_context(daily: dict, weekly: dict, confirm_lag: int = 2):
    """w_pos = position of a daily bar's price in the trailing 12-week range.

    Weekly bar stamped week w covers [w, w+7d) and is complete at w+7d; the
    study used a 2-week confirmation lag before the completed range is usable.
    Returns list aligned to daily bars, None where unavailable.
    """
    wt = weekly["timestamp"]
    wh, wl = weekly["high"], weekly["low"]
    n = len(daily["close"])
    out: list[float | None] = [None] * n
    # precompute: for each weekly index, range of 12 bars ending at that index
    for wi in range(11, len(wt)):
        usable_at = wt[wi] + timedelta(days=7 * confirm_lag)
        lo = min(wl[wi - 11:wi + 1])
        hi = max(wh[wi - 11:wi + 1])
        if hi <= lo:
            continue
        # applies to daily bars from usable_at until next weekly recompute
        pass
    # simpler: for each daily bar, find latest weekly bar usable at that date
    wj = 11
    for i, ts in enumerate(daily["timestamp"]):
        while wj + 1 < len(wt) and wt[wj + 1] + timedelta(days=7 * confirm_lag) <= ts:
            wj += 1
        usable = wt[wj] + timedelta(days=7 * confirm_lag)
        if ts < usable:
            continue
        lo = min(wl[wj - 11:wj + 1])
        hi = max(wh[wj - 11:wj + 1])
        if hi > lo:
            out[i] = (daily["close"][i] - lo) / (hi - lo)
    return out


def simulate(
    d: dict, wk: dict, k: float = K, short_filter: bool = True
) -> list[dict]:
    global K
    K = k
    h, l, c = d["high"], d["low"], d["close"]
    atr = sma_atr(d)
    raw = pivots(h, l)
    lg = legs(raw, atr)
    wpos = weekly_context(d, wk)
    ts = d["timestamp"]
    trades: list[dict] = []
    busy_until = -1
    for idx in range(len(lg) - 1):
        i, typ, price = lg[idx]
        ni, ntyp, nprice = lg[idx + 1]
        if ntyp == typ:
            continue
        # leg INTO ntyp pivot: down leg (H->L) = long, up leg (L->H) = short
        if ntyp == "L":
            direction = 1
        else:
            direction = -1
        ci = ni + 2
        if ci >= len(c) or ci <= busy_until:
            continue
        if direction < 0 and short_filter:
            wp = wpos[ci]
            if wp is None or wp >= 1.0:
                continue
        entry = c[ci]
        a = atr[ni]
        if a <= 0:
            continue
        stop = entry - direction * STOP * a
        target = entry + direction * TARGET * a
        exit_price = None
        exit_bar = -1
        outcome = "timeout"
        for j in range(1, HORIZON + 1):
            b = ci + j
            if b >= len(c):
                break
            # stop checked before target (conservative, same-bar ambiguity)
            if (direction > 0 and l[b] <= stop) or (direction < 0 and h[b] >= stop):
                exit_price, exit_bar, outcome = stop, b, "stop"
                break
            if (direction > 0 and h[b] >= target) or (direction < 0 and l[b] <= target):
                exit_price, exit_bar, outcome = target, b, "target"
                break
        if exit_price is None:
            if ci + HORIZON < len(c):
                exit_price, exit_bar, outcome = c[ci + HORIZON], ci + HORIZON, "timeout"
            else:
                continue
        r = direction * (exit_price - entry) / (STOP * a)
        trades.append({
            "entry_bar": ci, "exit_bar": exit_bar, "r": r,
            "outcome": outcome, "dir": direction, "date": ts[ci],
        })
        busy_until = exit_bar
    return trades


def summarise(trades: list[dict], label: str) -> None:
    n = len(trades)
    if not n:
        print(f"{label}: no trades")
        return
    rs = [t["r"] for t in trades]
    mean = statistics.mean(rs)
    sd = statistics.stdev(rs) if n > 1 else 0.0
    half = 1.96 * sd / (n ** 0.5)
    wins = sum(1 for r in rs if r > 0)
    print(f"{label}: n={n} E[R]={mean:+.3f} +-{half:.3f} "
          f"win={100 * wins / n:.1f}%")


def main() -> None:
    print("=== full 2003-2026, k=3.5, 1.5/3.0, 15 bars ===")
    all_t: list[dict] = []
    per_symbol = {}
    for s in SYMBOLS:
        d, w = load(s), load(s, "1w")
        if len(d["close"]) < 100:
            continue
        t = simulate(d, w)
        per_symbol[s] = t
        all_t.extend(t)
    summarise(all_t, "ALL")
    print("\nper-symbol:")
    for s, t in sorted(per_symbol.items()):
        if not t:
            continue
        rs = [x["r"] for x in t]
        m = statistics.mean(rs)
        sd = statistics.stdev(rs) if len(rs) > 1 else 0.0
        tt = m / (sd / len(rs) ** 0.5) if sd > 0 else 0.0
        print(f"  {s:7} n={len(t):4} E[R]={m:+.3f} t={tt:5.1f}")

    print("\noutcome mix:")
    from collections import Counter
    cnt = Counter(t["outcome"] for t in all_t)
    for k in ("target", "timeout", "stop"):
        sub = [t["r"] for t in all_t if t["outcome"] == k]
        if sub:
            print(f"  {k:8} {cnt[k]:4} ({100 * cnt[k] / len(all_t):.1f}%) "
                  f"avg {statistics.mean(sub):+.3f}")

    print("\n=== 5y window (2021-09-04..2026-09-04) ===")
    five = [t for t in all_t
            if t["date"] >= __import__("datetime").datetime(2021, 9, 4,
                                                            tzinfo=t["date"].tzinfo)]
    summarise(five, "5Y")


if __name__ == "__main__":
    main()
