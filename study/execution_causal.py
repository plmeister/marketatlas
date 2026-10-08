"""Causal pivot detection to avoid lookahead."""

from __future__ import annotations

K = 3.5
STOP, TARGET, HORIZON = 1.5, 3.0, 15


def build_prod_causal(d, k=3.5):
    from data_loader import sma_atr
    h, l = d["high"], d["low"]
    atr = sma_atr(d)
    pivots = []
    n = len(h)
    for i in range(2, n - 2):
        win_h = h[i - 2:i + 3]
        win_l = l[i - 2:i + 3]
        if h[i] == max(win_h) and h[i] > max(h[i - 2:i]) and h[i] > max(h[i + 1:i + 3]):
            pivots.append((i, "H", float(h[i]), i + 2))
        if l[i] == min(win_l) and l[i] < min(l[i - 2:i]) and l[i] < min(l[i + 1:i + 3]):
            pivots.append((i, "L", float(l[i]), i + 2))
    pivots = [p for p in pivots if p[3] < n]
    kept = []
    for pivot in sorted(pivots, key=lambda x: x[3]):
        i, typ, price, conf = pivot
        if not kept:
            kept.append(pivot)
            continue
        pi, ptyp, pprice, pconf = kept[-1]
        if typ == ptyp:
            if (typ == "H" and price > pprice) or (typ == "L" and price < pprice):
                kept[-1] = pivot
            continue
        ref = atr[conf] if conf < len(atr) else atr[-1]
        if ref > 0 and abs(price - pprice) >= k * ref:
            kept.append(pivot)
            continue
        if len(kept) >= 2 and kept[-2][1] == typ:
            p2i, p2t, p2p, p2c = kept[-2]
            if (typ == "H" and price > p2p) or (typ == "L" and price < p2p):
                kept[-2] = pivot
            kept.pop()
    return [(p[0], p[1], p[2]) for p in kept], atr
