#!/usr/bin/env python3
import sys
sys.path.insert(0, 'study')
from data_loader import load, sma_atr
from signal_check import weekly_context
import execution as ex
import statistics as st
from datetime import datetime, timezone
import json

SYMS = ["AUDCAD","AUDJPY","AUDNZD","AUDUSD","CADJPY","EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD","GBPAUD","GBPJPY","GBPNZD","GBPUSD","NZDCAD","NZDJPY","NZDUSD","USDCAD","USDCHF","XAGUSD","XAUUSD"]
wposs={s:weekly_context(load(s),load(s,'1w')) for s in SYMS if len(load(s)['close'])>=100}
allt=[]
for s in SYMS:
    d=load(s); d["_sym"]=s
    if len(d['close'])<100: continue
    lg,atr=ex.build_prod(d)
    allt+=ex.sim_base(d,lg,atr,wposs[s])

now = datetime.now(timezone.utc)
cut = now.replace(year=now.year-1)
window = [t for t in allt if t["date"]>=cut]
window.sort(key=lambda x:x["date"])
atrp=[t["atr"]/load(t["sym"])["close"][t["ci"]] for t in allt if t["atr"]>0]
mf = st.median(atrp)
cost = 0.0010/(1.5*mf)
capital = 100.0
for t in window:
    capital *= (1.0 + 0.01*(t['r']-cost))
out = {"timestamp": now.isoformat(), "trades": len(window), "capital": round(capital,2)}
print(json.dumps(out))

if __name__ == '__main__':
    import sys
    sys.path.insert(0, 'study')
    # recompute quickly (but it's slow; better to restructure) - leave as is
    pass
