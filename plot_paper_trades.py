#!/usr/bin/env python3
"""Plot charts with paper trade annotations."""
import sys
sys.path.insert(0, 'study')

import json
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import os

from data_loader import load


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--start', type=str, help='YYYY-MM-DD')
    parser.add_argument('--end', type=str, help='YYYY-MM-DD')
    parser.add_argument('--days', type=int, default=60, help='days to show if no range')
    parser.add_argument('--tag', default='paper-test-v1-causal')
    args = parser.parse_args()

    d = load(args.symbol)
    ts = d['timestamp']

    # find date range
    end_dt = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else ts[-1].date()
    start_dt = datetime.strptime(args.start, '%Y-%m-%d').date() if args.start else end_dt - timedelta(days=args.days)

    # find indices
    # build map
    start_idx = None
    end_idx = None
    for i,t in enumerate(ts):
        if t.date() >= start_dt and start_idx is None:
            start_idx = i
        if t.date() > end_dt:
            end_idx = i-1
            break
    if end_idx is None: end_idx = len(ts)-1
    if start_idx is None: start_idx = max(0, end_idx - args.days)

    # load paper trades
    state_dir = Path.home() / '.local/share/marketatlas/paper-logs' / args.tag
    events = state_dir / 'events.jsonl'
    entries = []
    exits = []
    if events.exists():
        for line in events.read_text().splitlines():
            try:
                ev = json.loads(line)
                evdt = datetime.fromisoformat(ev['date']).date() if ev.get('date') else None
                if evdt and evdt >= start_dt and evdt <= end_dt and ev['sym'] == args.symbol.upper():
                    if ev['type'] == 'entry':
                        entries.append(ev)
                    if ev['type'] == 'exit':
                        exits.append(ev)
            except Exception:
                pass

    # plot
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12,7))
    ax.plot(range(start_idx,end_idx+1), d['close'][start_idx:end_idx+1], linewidth=1, label='Close')
    for e in entries:
        # find idx
        for i,t in enumerate(ts[start_idx:end_idx+1], start_idx):
            if t.date() == datetime.fromisoformat(e['date']).date():
                ax.scatter(i, e['entry'], marker='^', color='g' if e['dir']>0 else 'r', s=80, label='_nolegend_')
                break
    for ex in exits:
        for i,t in enumerate(ts[start_idx:end_idx+1], start_idx):
            if t.date() == datetime.fromisoformat(ex['date']).date():
                ax.scatter(i, d['close'][i] if i < len(d['close']) else 0, marker='o', color='k', s=60, label='_nolegend_')
                break
    ax.set_title(f'{args.symbol} paper trades {start_dt} to {end_dt}')
    ax.grid(True, alpha=0.3)
    out = f'/tmp/{args.symbol.lower()}_paper_{start_dt}_{end_dt}.png'
    plt.tight_layout()
    plt.savefig(out)
    plt.close()
    print(out)


if __name__ == '__main__':
    main()
