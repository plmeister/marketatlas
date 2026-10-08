#!/usr/bin/env python3
import sys
sys.path.insert(0, 'study')
import pickle
import statistics as st
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
mf=st.median(atrp)
with open('/tmp/magrev_trades.pkl','wb') as f:
    pickle.dump({'allt':allt,'mf':mf}, f)
