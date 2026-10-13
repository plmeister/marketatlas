#!/usr/bin/env python3
"""Professional plotting with candles, trade overlays, indicators."""
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
    args = parser.parse_args()

    d = load(args.symbol)
    ts = d['timestamp']

    end_dt = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else ts[-1].date()
    start_dt = datetime.strptime(args.start, '%Y-%m-%d').date() if args.start else end_dt - timedelta(days=args.days)

    # find indices
    start_idx = end_idx = None
    for i,t in enumerate(ts):
        if t.date() >= start_dt and start_idx is None:
            start_idx = i
        if t.date() > end_dt:
            end_idx = i-1
            break
    if end_idx is None: end_idx = len(ts)-1
    if start_idx is None: start_idx = max(0,end_idx-args.days)

    # events
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

    # style dark
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(14,8))

    # candles
    dates = [mdates.date2num(t) for t in ts[start_idx:end_idx+1]]
    width = 0.6
    for i,(t,oc,oh,ol) in enumerate(zip(dates, d['open'][start_idx:end_idx+1], d['high'][start_idx:end_idx+1], d['low'][start_idx:end_idx+1])):
        if oc <= d['close'][start_idx:end_idx+1][i]:
            ax.plot([t,t],[ol,oh],'w', linewidth=0.8)
            ax.add_patch(Rectangle((t-width/2, min(oc,d['close'][start_idx:end_idx+1][i])), width, abs(d['close'][start_idx:end_idx+1][i]-oc), facecolor='#26a69a', edgecolor='white', linewidth=0.3))
        else:
            ax.plot([t,t],[ol,oh],'w', linewidth=0.8)
            ax.add_patch(Rectangle((t-width/2, min(oc,d['close'][start_idx:end_idx+1][i])), width, abs(d['close'][start_idx:end_idx+1][i]-oc), facecolor='#ef5350', edgecolor='white', linewidth=0.3))

    # annotate trades - simple
    for e in entries:
        for i,t in enumerate(ts[start_idx:end_idx+1], start_idx):
            if t.date() == datetime.fromisoformat(e['date']).date():
                ax.scatter(mdates.date2num(t), e['entry'], marker='^', color='lime', s=120, zorder=5)
                break

    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45, ha='right')
    ax.grid(True, alpha=0.2)
    ax.set_title(f'{args.symbol} - paper trades {start_dt} to {end_dt}')
    plt.tight_layout()
    out = f'/tmp/{args.symbol.lower()}_pro_{start_dt}_{end_dt}.png'
    plt.savefig(out, dpi=150)
    plt.close()
    print(out)


if __name__ == '__main__':
    main()
