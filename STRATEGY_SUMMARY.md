# Marketatlas Strategy System — Structured Summary

## 1. Signal Types (analysis/signals/ + strategy/signals)

| Signal | Uses Facts | Entry/Exit Logic (2-4 lines) |
|--------|-----------|------------------------------|
| `BreakoutSignal` (`analysis/signals/breakout_signal.py:18`) | `ChannelFact`, `TrendFact`, `ATRFact` | Entry: close pierces trailing N-day channel with compressing range (≤ compression_atlite
<tool_call>
<function=bash>
<parameter=command>
cd /home/scott/src/marketatlas && git log --oneline -1
</parameter