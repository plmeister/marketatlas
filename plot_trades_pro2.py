#!/usr/bin/env python3
"""Pro charting with SL/TP overlays and zones."""
import sys
sys.path.insert(0, 'study')

import json
from datetime import datetime, timedelta
from pathlib import Path
import argparse

from data_loader import load

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--start', type=str)
    parser.add_argument('--end', type=str)
    parser.add_argument('--days', type=int, default=60)
    parser.add_argument('--tag', default='paper-test-v1-causal')
    parser.add_argument('--show-zone', action='store_true', help='Show trade zone boxes')
    args = parser.parse_args()

    d = load(args.symbol)
    ts = d['timestamp']

    end_dt = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else ts[-1].date()
    start_dt = datetime.strptime(args.start, '%Y-%m-%d').date() if args.start else end_dt - timedelta(days=args.days)

    start_idx = end_idx = None
    for i,t in enumerate(ts):
        if t.date() >= start_dt and start_idx is None:
            start_idx = i
        if t.date() > end_dt:
            end_idx = i-1
            break
    if end_idx is None: end_idx = len(ts)-1
    if start_idx is None: start_idx = max(0,end_idx-args.days)

    events = Path.home() / '.local/share/marketatlas/paper-logs' / args.tag / 'events.jsonl'
    entries = []; exits = []
    if events.exists():
        for line in events.read_text().splitlines():
            try:
                ev = json.loads(line)
                if ev.get('type') in ('entry','exit') and ev.get('sym')==args.symbol.upper():
                    evdt = datetime.fromisoformat(ev['date']).date()
                    if evdt >= start_dt and evdt <= end_dt:
                        (entries if ev['type']=='entry' else exits).append(ev)
            except Exception:
                pass

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(14,8))

    dates = [mdates.date2num(t) for t in ts[start_idx:end_idx+1]]
    width = 0.6
    closes = d['close'][start_idx:end_idx+1]
    for i,(t,oc,oh,ol) in enumerate(zip(dates, d['open'][start_idx:end_idx+1], d['high'][start_idx:end_idx+1], d['low'][start_idx:end_idx+1])):
        c = closes[i]
        if oc <= c:
            ax.plot([t,t],[ol,oh],'w', linewidth=0.8)
            ax.add_patch(Rectangle((t-width/2, min(oc,c)), width, abs(c-oc), facecolor='#26a69a', edgecolor='white', linewidth=0.3))
        else:
            ax.plot([t,t],[ol,oh],'w', linewidth=0.8)
            ax.add_patch(Rectangle((t-width/2, min(oc,c)), width, abs(c-oc), facecolor='#ef5350', edgecolor='white', linewidth=0.3))

    # load state to get SL/TP levels
    state_path = Path.home() / '.local/share/marketatlas/paper-logs' / args.tag / 'state.json'
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
        for pos in state.get('open_positions', []):
            if pos['sym'] != args.symbol.upper(): continue
            # draw horizontal lines
            ax.axhline(y=pos['entry'], color='#4caf50', linestyle='-', alpha=0.6, linewidth=1.5, label='_nolegend_')
            ax.axhline(y=pos['stop'], color='#f44336', linestyle='--', alpha=0.8, linewidth=1.5, label='_nolegend_')
            ax.axhline(y=pos['target'], color='#2196f3', linestyle='--', alpha=0.8, linewidth=1.5, label='_nolegend_')
            ax.text(dates[-1], pos['entry'], f"Entry {pos['entry']:.5f}", color='#4caf50', va='bottom')
            ax.text(dates[-1], pos['stop'], f"SL {pos['stop']:.5f}", color='#f44336', va='top')
            ax.text(dates[-1], pos['target'], f"TP {pos['target']:.5f}", color='#2196f3', va='bottom')
            # zone box if requested
            if args.show_zone:
                try:
                    # find opened date
                    opened = datetime.fromisoformat(pos['opened']).date()
                    # find idx
                    for i,t in enumerate(ts[start_idx:end_idx+1], start_idx):
                        if t.date() == opened:
                            t_open = mdates.date2num(t)
                            break
                    else:
                        t_open = dates[0]
                    t_close = dates[-1]  # up to now
                    y0 = min(pos['stop'], pos['target'])
                    y1 = max(pos['stop'], pos['target'])
                    ax.add_patch(Rectangle((t_open, y0), t_close-t_open if t_close>t_open else width, y1-y0, facecolor='red' if pos['dir']<0 else 'green', alpha=0.1, edgecolor='gray', linewidth=0.5))
                except Exception:
                    pass

    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45, ha='right')
    ax.grid(True, alpha=0.2)
    ax.set_title(f'{args.symbol} - paper trades with SL/TP')
    plt.tight_layout()
    out = f'/tmp/{args.symbol.lower()}_pro2_{start_dt}_{end_dt}.png'
    plt.savefig(out, dpi=150)
    plt.close()
    print(out)


if __name__ == '__main__':
    main()
