#!/usr/bin/env python3
import sys
sys.path.insert(0, 'study')
import pickle
import json
from pathlib import Path
from datetime import datetime, timezone
import statistics as st

CACHE = Path('/tmp/magrev_trades.pkl')
STUDY_ROOT = Path('study')

if CACHE.exists():
    with open(CACHE,'rb') as f:
        data = pickle.load(f)
    allt, mf = data['allt'], data['mf']
else:
    from data_loader import load
    from signal_check import weekly_context
    import execution as ex
    SYMS = ["AUDCAD","AUDJPY","AUDNZD","AUDUSD","CADJPY","EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD","GBPAUD","GBPJPY","GBPNZD","GBPUSD","NZDCAD","NZDJPY","NZDUSD","USDCAD","USDCHF","XAGUSD","XAUUSD"]
    wposs={s:weekly_context(load(s),load(s,'1w')) for s in SYMS if len(load(s)['close'])>=100}
    allt=[]
    for s in SYMS:
        d=load(s); d["_sym"]=s
        if len(d['close'])<100: continue
        lg,atr=ex.build_prod(d)
        allt+=ex.sim_base(d,lg,atr,wposs[s])
    atrp=[t["atr"]/load(t["sym"])["close"][t["ci"]] for t in allt if t["atr"]>0]
    mf = st.median(atrp)
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
out = {"timestamp": now.isoformat(), "trades": len(window), "capital": round(capital,2), "cached": CACHE.exists()}
print(json.dumps(out))
