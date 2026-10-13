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


def find_idx_by_date(d, ts):
    # ts is list of timestamps in UTC
    for i,t in enumerate(ts):
        if t.date() == d: return i
    # fallback: find last <= d
    for i,t in enumerate(ts):
        if t.date() > d: return i-1
    return len(ts)-1


def process_day(proc_date, state, events_path):
    """Process a single day: close open positions if hit, then look for new signals."""
    # First, check and close open positions
    to_close = []
    remaining = []
    for pos in state['open_positions']:
        sym = pos['sym']
        try:
            d = load(sym)
        except Exception:
            remaining.append(pos)
            continue
        idx = find_idx_by_date(proc_date, d['timestamp'])
        if idx < pos['entry_idx']:
            remaining.append(pos)
            continue
        # check if stopped out or taken profit or timeout
        entry = pos['entry']
        stop = pos['stop']
        tgt = pos['target']
        dirn = pos['dir']
        # scan from entry_idx+1 to idx
        exited = False
        exit_px = None
        exit_reason = None
        for j in range(pos['entry_idx']+1, idx+1):
            low = d['low'][j]; high = d['high'][j]
            if dirn > 0:
                if low <= stop:
                    exited, exit_px, exit_reason = True, stop, 'stop'
                    break
                if high >= tgt:
                    exited, exit_px, exit_reason = True, tgt, 'target'
                    break
            else:
                if high >= stop:
                    exited, exit_px, exit_reason = True, stop, 'stop'
                    break
                if low <= tgt:
                    exited, exit_px, exit_reason = True, tgt, 'target'
                    break
        if not exited and idx >= pos['entry_idx'] + HORIZON:
            # timeout - exit at close
            exit_px = float(d['close'][idx])
            exit_reason = 'timeout'
            exited = True
        if exited:
            r = dirn * (exit_px - entry) / pos['atr_stop_unit'] if pos['atr_stop_unit'] > 0 else 0
            r_net = r - COST_R
            state['capital'] *= (1.0 + RISK_PCT/100.0 * r_net)
            state['trade_count'] += 1
            state['peak'] = max(state['peak'], state['capital'])
            if state['peak'] > 0:
                dd = (state['peak'] - state['capital']) / state['peak'] * 100.0
                state['maxdd'] = max(state['maxdd'], dd)
            ev = {
                'type':'exit',
                'date':proc_date.isoformat(),
                'sym':sym,
                'r':r,
                'r_net':r_net,
                'reason':exit_reason,
                'capital':state['capital']
            }
            with open(events_path,'a') as f:
                f.write(json.dumps(ev)+'\n')
            # closed
        else:
            remaining.append(pos)
    state['open_positions'] = remaining

    # Look for new signals at proc_date? Entry is at ci=ni+2; we need to detect signals where ci == idx of proc_date?
    # But pivots are detected from causal build on available history. For safety, only look if it's end of day and we want to enter next? 
    # The strategy enters at close of confirmation bar (ci). So if ci corresponds to proc_date, the trade is entered at close of proc_date.
    # To be conservative with daily bars, we enter on confirmation close.
    for sym in SYMS:
        try:
            d = load(sym)
            w = load(sym,'1w')
        except Exception:
            continue
        idx = find_idx_by_date(proc_date, d['timestamp'])
        if idx < 0: continue
        # need wpos
        try:
            wc = weekly_context(d,w)
        except Exception:
            continue
        # build pivots causally on full data up to len(d)? but d is full; causal is fine
        lg, atr = build_prod_causal(d)
        # look for transitions ending at pivot ni such that ci = ni+2 == idx?
        for i in range(len(lg)-1):
            ni, ntyp, _ = lg[i+1]
            ci = ni + 2
            if ci != idx: continue
            # check if taken
            # direction
            typ_cur = lg[i][1]
            if lg[i+1][1] == typ_cur: continue
            direction = 1 if lg[i+1][1] == 'L' else -1
            # check if we already have position in this sym? or just busy
            # busy: if any open pos for sym and entry_idx <= idx <= exit_idx? not tracked; keep simple - don't open if already have open pos in same sym
            has_open = any(p['sym']==sym for p in state['open_positions'])
            if has_open: continue
            # short filter
            if direction < 0:
                wpv = wc[ci] if hasattr(wc, '__getitem__') else None
                # wc is list
                try:
                    wpv = wc[ci] if ci < len(wc) else wc[-1]
                except:
                    wpv = None
                if wpv is None or wpv >= SHORT_WPOS_THR:
                    continue
            a = atr[ni] if ni < len(atr) else atr[-1]
            if a <= 0: continue
            entry = float(d['close'][ci])
            sp = STOP_ATR * a
            tp = TP_ATR * a
            stop_px = entry - direction * sp
            tgt_px = entry + direction * tp
            # open position
            pos = {
                'sym': sym,
                'dir': direction,
                'entry': entry,
                'entry_idx': ci,
                'stop': stop_px,
                'target': tgt_px,
                'atr_stop_unit': sp,
                'opened': proc_date.isoformat()
            }
            state['open_positions'].append(pos)
            ev = {'type':'entry','date':proc_date.isoformat(),'sym':sym,'dir':direction,'entry':entry}
            with open(events_path,'a') as f:
                f.write(json.dumps(ev)+'\n')


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
