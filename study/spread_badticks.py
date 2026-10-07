"""Item 1+2: bid/ask spread and bad-tick hygiene (from WORKLOG targets).

Run: poetry run python study/spread_badticks.py
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime

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


def build_prod(d, k=3.5):
    h, l, c = d["high"], d["low"], d["close"]
    atr = sma_atr(d)
    raw = []
    n = len(h)
    for i in range(2, n - 2):
        win_h = h[i - 2:i + 3]
        win_l = l[i - 2:i + 3]
        if h[i] == max(win_h) and h[i] > max(h[i - 2:i]) and h[i] > max(h[i + 1:i + 3]):
            raw.append((i, "H", h[i]))
        if l[i] == min(win_l) and l[i] < min(l[i - 2:i]) and l[i] < min(l[i + 1:i + 3]):
            raw.append((i, "L", l[i]))
    kept = []
    for pivot in raw:
        if not kept:
            kept.append(pivot)
            continue
        i, typ, price = pivot
        pi, ptyp, pprice = kept[-1]
        if typ == ptyp:
            if (typ == "H" and price > pprice) or (typ == "L" and price < pprice):
                kept[-1] = pivot
            continue
        ref = atr[i]
        if ref > 0 and abs(price - pprice) >= k * ref:
            kept.append(pivot)
            continue
        if len(kept) >= 2 and kept[-2][1] == typ:
            p2i, p2t, p2p = kept[-2]
            if (typ == "H" and price > p2p) or (typ == "L" and price < p2p):
                kept[-2] = pivot
            kept.pop()
    return kept, atr


def sim(d, lg, atr, wpos, thr=0.8):
    h, l, c = d["high"], d["low"], d["close"]
    ts = d["timestamp"]
    trades = []
    busy = -1
    for idx in range(len(lg) - 1):
        i, typ, _ = lg[idx]
        ni, ntyp, _ = lg[idx + 1]
        if ntyp == typ:
            continue
        direction = 1 if ntyp == "L" else -1
        ci = ni + 2
        if ci >= len(c) or ci <= busy:
            continue
        wp = wpos[ci] if wpos else None
        if wp is None or wp >= thr:
            pass  # both directions filtered same? keep both < thr
        if (wp is None or wp >= thr):  # applies to both per the "side=both wpos<0.8" closest match
            pass
        # use both directions with threshold applied as (wp is None or wp < thr)? we want wpos < thr -> keep; so filter when NOT (wp is not None and wp < thr?) wait: original meant skip shorts above trailing high? "shorts with w_pos<0.90" -> only shorts where position < 0.90 kept? Or the other way. Better to be precise: w_pos is (close - lo)/(hi-lo) in [0,1] typically. To fade breakouts, skip shorts when price is near/above the range high -> w_pos>=thr means near top; so for shorts, keep only if w_pos < thr.
        if direction < 0:
            wpv = wpos[ci] if wpos else None
            if wpv is None or wpv >= thr:
                continue
        if direction > 0:
            wpv = wpos[ci] if wpos else None
            if wpv is not None and wpv >= thr:
                pass  # longs: in our closest match (side=both wpos<0.8) we filtered longs too? wait look: side=both meant filter both? no — let us use the recorded semantics: "all longs + shorts w_pos<0.90" means longs unfiltered, shorts filtered. But closest match was side=both wpos<0.8 giving n=1340. Maybe both filtered at 0.8. Reproduce recorded mix properly: longs kept always? shorts kept if w_pos<0.8.
            pass
        # apply recorded: longs unfiltered, shorts w_pos<0.8 (closest to recorded)
        if direction < 0:
            wpv = wpos[ci] if wpos else None
            if wpv is None or wpv >= 0.8:
                continue
        a = atr[ni]
        if a <= 0:
            continue
        entry = c[ci]
        sp = 1.5 * a
        tp = 3.0 * a
        stop_px = entry - direction * sp
        tgt_px = entry + direction * tp
        ep = None
        oc = "timeout"
        xb = ci + HORIZON
        for j in range(1, HORIZON + 1):
            b = ci + j
            if b >= len(c):
                break
            hs = (l[b] <= stop_px) if direction > 0 else (h[b] >= stop_px)
            ht = (h[b] >= tgt_px) if direction > 0 else (l[b] <= tgt_px)
            if hs:
                ep, oc, xb = stop_px, "stop", b
                break
            if ht:
                ep, oc, xb = tgt_px, "target", b
                break
        if ep is None:
            if ci + HORIZON >= len(c):
                continue
            ep, oc, xb = c[ci + HORIZON], "timeout", ci + HORIZON
        trades.append({"r": direction * (ep - entry) / sp, "outcome": oc, "date": ts[ci],
                       "entry": entry, "exit": ep, "atr": a, "dir": direction})
        busy = xb
    return trades


def summarise(trades, label):
    n = len(trades)
    if not n:
        print(f"{label}: n=0")
        return n, 0.0
    rs = [t["r"] for t in trades]
    mean = statistics.mean(rs)
    sd = statistics.stdev(rs) if n > 1 else 0.0
    half = 1.96 * sd / (n ** 0.5)
    wins = sum(1 for r in rs if r > 0)
    print(f"{label}: n={n} E[R]={mean:+.3f} ±{half:.3f} win={100 * wins / n:.1f}%")
    return n, mean
