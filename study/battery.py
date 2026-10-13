#!/usr/bin/env python3
"""Full-history aggregate + walk-forward for the magnitude-reversion study.

Causal pivots (build_prod_causal), 1.5/3.0 ATR, 15-bar max-hold.
Max-hold expiry with neither level touched = CANCEL at R=0 (no cost),
matching TradeBook._cancel_open.

Run: poetry run python study/battery.py
"""
from __future__ import annotations

import statistics as st
import sys
from datetime import datetime, timezone

sys.path.insert(0, "study")

from data_loader import load  # noqa: E402
from execution import sim_base  # noqa: E402
from execution_causal import build_prod_causal  # noqa: E402
from signal_check import weekly_context  # noqa: E402

SYMS = ["AUDCAD","AUDJPY","AUDNZD","AUDUSD","CADJPY","EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD","GBPAUD","GBPJPY","GBPNZD","GBPUSD","NZDCAD","NZDJPY","NZDUSD","USDCAD","USDCHF","XAGUSD","XAUUSD"]


def load_all():
    trades = []
    atrp = []
    for s in SYMS:
        d, w = load(s), load(s, "1w")
        if len(d["close"]) < 100:
            continue
        wc = weekly_context(d, w)
        d2 = load(s)
        d2["_sym"] = s
        lg, atr = build_prod_causal(d2)
        tr = sim_base(d2, lg, atr, wc)
        trades += tr
        for t in tr:
            if t["atr"] > 0:
                atrp.append(t["atr"] / d2["close"][t["ci"]])
    return trades, st.median(atrp)


def stats(tr, cost):
    n = len(tr)
    cancels = [t for t in tr if t["outcome"] == "cancel"]
    decided = [t for t in tr if t["outcome"] != "cancel"]
    r_all = [t["r"] - (0.0 if t["outcome"] == "cancel" else cost) for t in tr]
    r_dec = [t["r"] - cost for t in decided]
    wins = sum(1 for t in decided if t["r"] > 0)
    return {
        "n": n,
        "cancel": len(cancels),
        "decided": len(decided),
        "win%": round(100.0 * wins / len(decided), 1) if decided else 0.0,
        "E[R] incl cancel": round(st.mean(r_all), 3) if n else 0.0,
        "E[R] excl cancel": round(st.mean(r_dec), 3) if r_dec else 0.0,
    }


def main():
    trades, mf = load_all()
    cost = 0.0010 / (1.5 * mf) if mf else 0.089
    trades.sort(key=lambda t: t["date"])
    now = datetime.now(timezone.utc)

    def cut(year):
        return datetime(year, 1, 1, tzinfo=timezone.utc)

    print(f"median ATR/price {mf:.5f}  costR(10pip) {cost:.4f}")
    print(f"full  : {stats(trades, cost)}")
    last10 = [t for t in trades if t["date"] >= (now.replace(year=now.year - 10))]
    print(f"10y   : {stats(last10, cost)}")
    train = [t for t in trades if t["date"] < datetime(2023, 9, 1, tzinfo=timezone.utc)]
    valid = [t for t in trades if datetime(2023, 9, 1, tzinfo=timezone.utc) <= t["date"] < datetime(2025, 1, 1, tzinfo=timezone.utc)]
    test = [t for t in trades if t["date"] >= datetime(2025, 1, 1, tzinfo=timezone.utc)]
    print(f"train : {stats(train, cost)}")
    print(f"valid : {stats(valid, cost)}")
    print(f"test  : {stats(test, cost)}")


if __name__ == "__main__":
    main()
