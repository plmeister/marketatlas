#!/usr/bin/env python3
"""Stateful EOD paper trading tick.

Advances by *bar* (not calendar day). Each run:
  1. loads available candles per symbol,
  2. finds bars newer than the last processed bar,
  3. for each new bar (oldest first): first resolves exits on any open
     position for that symbol, then looks for a new entry whose confirmation
     bar (ci) is exactly this bar,
  4. records entries/exits with the *bar* date and persists state.

Only data up to and including the current bar is ever consulted, so the
decision path matches what a live EOD trader could have known at that close.
"""
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
    allt = []
    for s in SYMS[:3]:
        d, w = load(s), load(s, '1w')
        if len(d['close']) >= 100:
            wc = weekly_context(d, w)
            lg, atr = build_prod_causal(d)
            from execution import sim_base
            allt += sim_base(d, lg, atr, wc)
    atrp = []
    for t in allt[:500]:
        try:
            c = load(t['sym'])['close'][t['ci']]
            if t['atr'] > 0:
                atrp.append(t['atr'] / c)
        except Exception:
            pass
    COST_R = 0.0010 / (1.5 * (st.median(atrp) if atrp else 0.001))
except Exception:
    COST_R = 0.089


def new_state():
    return {
        'capital': 100.0,
        'peak': 100.0,
        'maxdd': 0.0,
        'last_bar_date': None,
        'open_positions': [],
        'trade_count': 0,
    }


def append_event(events_path, ev):
    with open(events_path, 'a') as f:
        f.write(json.dumps(ev) + '\n')


def resolve_exits(state, sym, d, idx, events_path):
    """Check open position for `sym` against bar `idx`; close if hit.

    Returns True if a position was closed on this bar (so no new entry may
    open on the same bar, matching the one-position-per-symbol rule).
    """
    remaining = []
    closed = False
    for pos in state['open_positions']:
        if pos['sym'] != sym:
            remaining.append(pos)
            continue
        dirn = pos['dir']
        low = d['low'][idx]
        high = d['high'][idx]
        exit_px = None
        reason = None
        if dirn > 0:
            if low <= pos['stop']:
                exit_px, reason = pos['stop'], 'stop'
            elif high >= pos['target']:
                exit_px, reason = pos['target'], 'target'
        else:
            if high >= pos['stop']:
                exit_px, reason = pos['stop'], 'stop'
            elif low <= pos['target']:
                exit_px, reason = pos['target'], 'target'
        if exit_px is None and idx >= pos['entry_idx'] + HORIZON:
            exit_px, reason = float(d['close'][idx]), 'timeout'
        if exit_px is None:
            remaining.append(pos)
            continue
        unit = pos['atr_stop_unit']
        r = dirn * (exit_px - pos['entry']) / unit if unit > 0 else 0.0
        r_net = r - COST_R
        state['capital'] *= (1.0 + RISK_PCT / 100.0 * r_net)
        state['trade_count'] += 1
        state['peak'] = max(state['peak'], state['capital'])
        if state['peak'] > 0:
            dd = (state['peak'] - state['capital']) / state['peak'] * 100.0
            state['maxdd'] = max(state['maxdd'], dd)
        append_event(events_path, {
            'type': 'exit',
            'date': d['timestamp'][idx].date().isoformat(),
            'sym': sym,
            'dir': dirn,
            'r': round(r, 4),
            'r_net': round(r_net, 4),
            'reason': reason,
            'capital': round(state['capital'], 2),
        })
        closed = True
    state['open_positions'] = remaining
    return closed


def find_new_entries(state, sym, d, idx, lg, atr, wc, events_path):
    """Open a position if a pivot transition confirms exactly on bar `idx`."""
    if any(p['sym'] == sym for p in state['open_positions']):
        return
    for i in range(len(lg) - 1):
        cur_i, cur_t, _ = lg[i]
        ni, ntyp, _ = lg[i + 1]
        if ntyp == cur_t:
            continue
        ci = ni + 2
        if ci != idx:
            continue
        direction = 1 if ntyp == 'L' else -1
        if direction < 0:
            wpv = wc[ci] if ci < len(wc) else (wc[-1] if wc else None)
            if wpv is None or wpv >= SHORT_WPOS_THR:
                continue
        a = atr[ni] if ni < len(atr) else atr[-1]
        if a <= 0:
            continue
        entry = float(d['close'][ci])
        sp = STOP_ATR * a
        tp = TP_ATR * a
        pos = {
            'sym': sym,
            'dir': direction,
            'entry': entry,
            'entry_idx': ci,
            'stop': entry - direction * sp,
            'target': entry + direction * tp,
            'atr_stop_unit': sp,
            'opened': d['timestamp'][ci].date().isoformat(),
        }
        state['open_positions'].append(pos)
        append_event(events_path, {
            'type': 'entry',
            'date': d['timestamp'][ci].date().isoformat(),
            'sym': sym,
            'dir': direction,
            'entry': entry,
            'stop': pos['stop'],
            'target': pos['target'],
        })
        return


def process_bar(state, sym, d, idx, wc, events_path):
    closed = resolve_exits(state, sym, d, idx, events_path)
    if closed:
        return
    lg, atr = build_prod_causal({k: v[:idx + 1] for k, v in d.items() if hasattr(v, '__len__')})
    find_new_entries(state, sym, d, idx, lg, atr, wc, events_path)


def write_summary(state, state_dir):
    with open(state_dir / 'summary.json', 'w') as f:
        json.dump({
            'capital': round(state['capital'], 2),
            'peak': round(state['peak'], 2),
            'maxdd': round(state['maxdd'], 2),
            'trade_count': state['trade_count'],
            'last_bar_date': state['last_bar_date'],
            'open_positions': len(state['open_positions']),
        }, f, indent=2)


def main():
    tag = os.environ.get('PAPER_TAG', 'paper-test-v1-causal')
    state_dir = Path(os.path.expanduser('~/.local/share/marketatlas/paper-logs')) / tag
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / 'state.json'
    events_path = state_dir / 'events.jsonl'

    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
        state.setdefault('last_bar_date', state.pop('last_processed', None))
    else:
        state = new_state()

    cold_start = state['last_bar_date'] is None

    # Build the set of bars to process across all symbols, ordered by date.
    # On cold start, only walk a recent warmup window (don't replay history).
    work = []  # (bar_date, sym, idx, d, wc)
    latest = None
    for sym in SYMS:
        try:
            d = load(sym)
            w = load(sym, '1w')
        except Exception:
            continue
        if len(d['timestamp']) == 0:
            continue
        try:
            wc = weekly_context(d, w)
        except Exception:
            continue
        sym_latest = d['timestamp'][-1].date()
        if latest is None or sym_latest > latest:
            latest = sym_latest
        for idx, t in enumerate(d['timestamp']):
            bd = t.date()
            if cold_start:
                if (sym_latest - bd).days <= 40:
                    work.append((bd, sym, idx, d, wc))
            elif bd > date.fromisoformat(state['last_bar_date']):
                work.append((bd, sym, idx, d, wc))

    work.sort(key=lambda x: (x[0], x[1]))

    if not work:
        append_event(events_path, {'type': 'heartbeat', 'ts': datetime.now(timezone.utc).isoformat()})
        write_summary(state, state_dir)
        return

    for bd, sym, idx, d, wc in work:
        process_bar(state, sym, d, idx, wc, events_path)
        state['last_bar_date'] = bd.isoformat()

    with open(state_path, 'w') as f:
        json.dump(state, f, indent=2)
    write_summary(state, state_dir)


if __name__ == '__main__':
    main()
