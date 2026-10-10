#!/usr/bin/env python3
"""Stateful EOD paper trading tick."""
import sys
sys.path.insert(0, 'study')

import json
import os
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

from data_loader import load
from execution_causal import build_prod_causal
from signal_check import weekly_context
import statistics as st

SYMS = ["AUDCAD","AUDJPY","AUDNZD","AUDUSD","CADJPY","EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD","GBPAUD","GBPJPY","GBPNZD","GBPUSD","NZDCAD","NZDJPY","NZDUSD","USDCAD","USDCHF","XAGUSD","XAUUSD"]
STOP_ATR = 1.5
TP_ATR = 3.0
HORIZON = 15
SHORT_WPOS_THR = 0.8
RISK_PCT = 1.0

# compute cost
try:
    allt=[]
    for s in SYMS[:3]:
        d,w = load(s), load(s,'1w')
        if len(d['close'])>=100:
            wc = weekly_context(d,w)
            lg,atr = build_prod_causal(d)
            from execution import sim_base
            allt += sim_base(d,lg,atr,wc)
    atrp=[]
    for t in allt[:500]:
        try:
            c = load(t['sym'])['close'][t['ci']]
            if t['atr']>0: atrp.append(t['atr']/c)
        except: pass
    COST_R = 0.0010/(1.5*(st.median(atrp) if atrp else 0.001))
except Exception:
    COST_R = 0.089


def daterange(s,e):
    cur = s
    while cur < e:
        yield cur
        cur += timedelta(days=1)


def process_day(proc_date, state, events_path):
    # TODO: implement proper stateful processing
    # For now, just record that we processed
    with open(events_path, 'a') as f:
        f.write(json.dumps({'type':'tick','date':proc_date.isoformat()})+'\n')


def main():
    tag = os.environ.get('PAPER_TAG', 'paper-test-v1-causal')
    state_dir = Path(os.path.expanduser('~/.local/share/marketatlas/paper-logs')) / tag
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / 'state.json'
    events_path = state_dir / 'events.jsonl'

    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
    else:
        state = {'capital':100.0,'peak':100.0,'maxdd':0.0,'last_processed':None,'open_positions':[],'trade_count':0}

    now_dt = datetime.now(timezone.utc)
    today = now_dt.date()
    last = date.fromisoformat(state['last_processed']) if state['last_processed'] else today - timedelta(days=7)

    if last >= today:
        with open(events_path, 'a') as f:
            f.write(json.dumps({'type':'heartbeat','ts':now_dt.isoformat()})+'\n')
        return

    for proc_date in daterange(last+timedelta(days=1), today):
        process_day(proc_date, state, events_path)

    state['last_processed'] = today.isoformat()
    with open(state_path,'w') as f:
        json.dump(state,f,indent=2)


if __name__ == '__main__':
    main()
