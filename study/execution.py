"""Items 1-4: spread, bad ticks, hourly stop bars, walk-forward."""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime

from data_loader import load, sma_atr
from signal_check import weekly_context

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
    h, l = d["high"], d["low"]
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


def sim_base(d, lg, atr, wpos, thr=0.8):
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
        if direction < 0:
            wpv = wpos[ci] if wpos else None
            if wpv is None or wpv >= thr:
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
            # Max-hold expiry with neither stop nor target touched: the
            # strategy closes the position at market, so the exit price is the
            # bar's close. Max-hold is a strategy rule, not a broker feature.
            ep, oc, xb = c[ci + HORIZON], "timeout", ci + HORIZON
        trades.append({
            "r": direction * (ep - entry) / sp,
            "outcome": oc,
            "date": ts[ci],
            "entry": entry,
            "exit": ep,
            "atr": a,
            "dir": direction,
            "ci": ci,
            "xb": xb,
            "sym": d.get("_sym"),
        })
        busy = xb
    return trades
