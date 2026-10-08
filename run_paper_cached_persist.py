#!/usr/bin/env python3
import sys
sys.path.insert(0, 'study')
import pickle
import json
from pathlib import Path
from datetime import datetime, timezone
import statistics as st
import os

CACHE = Path(os.path.expanduser('~/.local/share/marketatlas/data/magrev_trades.pkl'))

# Always rebuild from current data to pick up new bars
from data_loader import load
from signal_check import weekly_context
from execution_causal import build_prod_causal
from execution import sim_base

SYMS = ["AUDCAD","AUDJPY","AUDNZD","AUDUSD","CADJPY","EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD","GBPAUD","GBPJPY","GBPNZD","GBPUSD","NZDCAD","NZDJPY","NZDUSD","USDCAD","USDCHF","XAGUSD","XAUUSD"]
wposs={s:weekly_context(load(s),load(s,'1w')) for s in SYMS if len(load(s)['close'])>=100}
allt=[]
for s in SYMS:
    d=load(s); d["_sym"]=s
    if len(d['close'])<100: continue
    lg,atr=build_prod_causal(d)
    allt+=sim_base(d,lg,atr,wposs[s])
atrp=[t["atr"]/load(t["sym"])["close"][t["ci"]] for t in allt if t["atr"]>0]
mf = st.median(atrp)
# update cache for other uses
CACHE.parent.mkdir(parents=True, exist_ok=True)
with open(CACHE,'wb') as f:
    pickle.dump({'allt':allt,'mf':mf}, f)

now = datetime.now(timezone.utc)
cut = now.replace(year=now.year-1)
window = [t for t in allt if t["date"]>=cut]
window.sort(key=lambda x:x["date"])
cost = 0.0010/(1.5*mf)
capital = 100.0
for t in window:
    capital *= (1.0 + 0.01*(t['r']-cost))
out = {"timestamp": now.isoformat(), "trades": len(window), "capital": round(capital,2), "version":"causal-v1"}
print(json.dumps(out))
