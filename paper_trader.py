#!/usr/bin/env python3
"""Stateful EOD paper trader - only uses data available up to decision time."""
import sys
sys.path.insert(0, 'study')

import json
import os
from datetime import datetime, timezone, timedelta
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


def get_cost_factor():
    # compute once
    try:
        allt = []
        for s in SYMS[:5]:
            d,w = load(s), load(s,'1w')
            if len(d['close'])>=100:
                wc = weekly_context(d,w)
                lg,atr = build_prod_causal(d)
                from execution import sim_base
                allt += sim_base(d,lg,atr,wc)
        atrp = []
        for t in allt[:1000]:
            try:
                c = load(t['sym'])['close'][t['ci']]
                if t['atr']>0: atrp.append(t['atr']/c)
            except: pass
        mf = st.median(atrp) if atrp else 0.001
        return 0.0010/(1.5*mf)
    except:
        return 0.089


COST_R = get_cost_factor()
