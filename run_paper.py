#!/usr/bin/env python3
from data_loader import load, sma_atr
from signal_check import weekly_context
import execution as ex
import statistics as st
from datetime import datetime, timezone
import json
import os

SYMS = ["AUDCAD","AUDJPY","AUDNZD","AUDUSD","CADJPY","EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD","GBPAUD","GBPJPY","GBPNZD","GBPUSD","NZDCAD","NZDJPY","NZDUSD","USDCAD","USDCHF","XAGUSD","XAUUSD"]
wposs={}
allt=[]
# load
for s in SYMS:
    d,w=load(s),load(s,'1w')
    if len(d['close'])<100: continue
    wposs[s]=weekly_context(d,w)
    d2=load(s); d2["_sym"]=s
    lg,atr=ex.build_prod(d2)
    allt+=ex.sim_base(d2,lg,atr,wposs[s])

# last 12 months
now = datetime.now(timezone.utc)
cut = datetime(now.year-1, now.month, now.day, tzinfo=timezone.utc) if now.day>=4 else datetime(now.year-1 if now.month>1 else now.year-2, (now.month-1) or 12, 1, tzinfo=timezone.utc)
# simple: last 365 days
cut = now.replace(year=now.year-1)
window = [t for t in allt if t["date"]>=cut]
window.sort(key=lambda x:x["date"])

# costs
atrp=[t["atr"]/load(t["sym"])["close"][t["ci"]] for t in allt if t["atr"]>0]
mf = st.median(atrp)
cost = 0.0010/(1.5*mf) # 10pip
capital = 100.0
results = []
for t in window:
    cap_before = capital
    capital *= (1.0 + 0.01*(t['r']-cost))
    results.append({
        "date": t["date"].isoformat(),
        "sym": t["sym"],
        "r_net": t["r"]-cost,
        "capital": capital,
        "pnl_pct": (capital/cap_before-1.0)*100
    })

out = {
    "start_capital": 100.0,
    "end_capital": capital,
    "trades": len(results),
    "cost_pip": 10,
    "timestamp": now.isoformat(),
}
with open('/tmp/paper_latest.json','w') as f:
    json.dump({**out, "trades": results[-20:]}, f, indent=2)
print(f"done: {len(window)} trades, cap £{capital:.2f}")
