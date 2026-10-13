#!/usr/bin/env python3
"""Pro chart: candlesticks + entry/stop/target lines + trade zones.

Zones are split at the entry so profit (green) and loss (red) rectangles
never overlap (overlapping translucent green+red looked muddy yellow).
"""
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

GREEN = '#00e676'
RED = '#ff1744'
BLUE = '#40c4ff'
HORIZON = 15


def load_trades(tag, symbol):
    events = Path.home() / '.local/share/marketatlas/paper-logs' / tag / 'events.jsonl'
    entries = []
    exits = []
    if not events.exists():
        return entries, exits
    for line in events.read_text().splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get('sym') != symbol.upper():
            continue
        if ev.get('type') == 'entry':
            entries.append(ev)
        elif ev.get('type') == 'exit':
            exits.append(ev)
    return entries, exits


def pair_trades(entries, exits):
    trades = []
    used = set()
    for e in sorted(entries, key=lambda x: x['date']):
        match = None
        for j, x in enumerate(sorted(exits, key=lambda x: x['date'])):
            if x['sym'] == e['sym'] and x['date'] >= e['date'] and id(x) not in used:
                match = x
                used.add(id(x))
                break
        trades.append((e, match))
    return trades


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--start', type=str)
    parser.add_argument('--end', type=str)
    parser.add_argument('--days', type=int, default=60)
    parser.add_argument('--tag', default='paper-test-v1-causal')
    parser.add_argument('--show-zone', action='store_true')
    parser.add_argument('--no-candles', action='store_true')
    args = parser.parse_args()

    d = load(args.symbol)
    ts = d['timestamp']

    end_dt = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else ts[-1].date()
    start_dt = datetime.strptime(args.start, '%Y-%m-%d').date() if args.start else end_dt - timedelta(days=args.days)

    start_idx = next((i for i, t in enumerate(ts) if t.date() >= start_dt), 0)
    end_idx = next((i for i, t in enumerate(ts) if t.date() > end_dt), len(ts)) - 1

    def dnum(dt):
        return mdates.date2num(dt)

    entries, exits = load_trades(args.tag, args.symbol)
    trades = pair_trades(entries, exits)

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(15, 8))

    width = 0.6
    for i in range(start_idx, end_idx + 1):
        t = dnum(ts[i].date())
        o, h, l, c = d['open'][i], d['high'][i], d['low'][i], d['close'][i]
        col = GREEN if c >= o else RED
        ax.plot([t, t], [l, h], color=col, linewidth=0.8, zorder=2)
        ax.add_patch(Rectangle((t - width / 2, min(o, c)), width, abs(c - o) or 1e-9,
                               facecolor=col, edgecolor=col, linewidth=0.4, zorder=2))

    max_label_x = end_dt
    for entry, exit_ev in trades:
        opened = datetime.fromisoformat(entry['date']).date()
        if opened < start_dt or opened > end_dt:
            continue
        # locate entry bar index so the max-span (15 *bars*) is exact
        e_idx = next((i for i, t in enumerate(ts) if t.date() == opened), None)
        if e_idx is None:
            continue
        t_open = dnum(ts[e_idx].date())
        span_idx = min(e_idx + HORIZON, len(ts) - 1)
        maxspan_date = min(ts[span_idx].date(), end_dt)
        if exit_ev:
            closed = datetime.fromisoformat(exit_ev['date']).date()
            t_close = dnum(min(closed, maxspan_date))
        else:
            t_close = dnum(maxspan_date)

        e = entry['entry']
        s = entry['stop']
        tp = entry['target']
        dirn = entry['dir']

        ax.plot([t_open, t_close], [e, e], color=GREEN, linewidth=1.4, zorder=3)
        ax.plot([t_open, t_close], [s, s], color=RED, linewidth=1.2, linestyle='--', zorder=3)
        ax.plot([t_open, t_close], [tp, tp], color=BLUE, linewidth=1.2, linestyle='--', zorder=3)

        if args.show_zone:
            if dirn >= 0:
                ax.add_patch(Rectangle((t_open, e), t_close - t_open, max(tp - e, 0),
                                       facecolor=GREEN, alpha=0.18, edgecolor=GREEN, linewidth=0.6, zorder=1))
                ax.add_patch(Rectangle((t_open, s), t_close - t_open, max(e - s, 0),
                                       facecolor=RED, alpha=0.18, edgecolor=RED, linewidth=0.6, zorder=1))
            else:
                ax.add_patch(Rectangle((t_open, tp), t_close - t_open, max(e - tp, 0),
                                       facecolor=GREEN, alpha=0.18, edgecolor=GREEN, linewidth=0.6, zorder=1))
                ax.add_patch(Rectangle((t_open, e), t_close - t_open, max(s - e, 0),
                                       facecolor=RED, alpha=0.18, edgecolor=RED, linewidth=0.6, zorder=1))

        for level, col, lab in ((e, GREEN, 'Entry'), (s, RED, 'SL'), (tp, BLUE, 'TP')):
            ax.annotate(f"{lab} {level:.5f}", xy=(t_close, level), xycoords='data',
                        xytext=(6, 0), textcoords='offset points',
                        color=col, fontsize=8, va='center', ha='left', zorder=5)
        if t_close > dnum(max_label_x):
            max_label_x = mdates.num2date(t_close).date()

    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    ax.set_xlim(dnum(start_dt) - 0.7, dnum(end_dt) + 0.7)
    plt.xticks(rotation=45, ha='right')
    ax.grid(True, alpha=0.2)
    ax.set_title(f'{args.symbol}  paper trades  ({start_dt} to {end_dt})')
    ax.set_ylabel('price')
    fig.subplots_adjust(right=0.85, bottom=0.18)
    out = f'/tmp/{args.symbol.lower()}_pro2.png'
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close()
    print(out)


if __name__ == '__main__':
    main()
