"""Results summary for the four remaining items.

NOTE (2026-10-13): max-hold expiry with neither stop nor target touched is a
MARKET CLOSE at the bar's price (realized +/- R), matching the restored
TradeBook behaviour. Max-hold is a strategy rule, not a broker feature, so the
position must be closed at the current price — it is NOT a free cancel.
Re-run `study/battery.py` for current figures.

Item 1 (bid/ask): MF=0.753% ATR (EURUSD-like). Cost in R = spread/(1.5*MF).
  10 pip (0.0010): costR=0.0886 -> E[R]=+1.240, win 83.2% (n=1402 full)
  20 pip: 0.1771 -> +1.151, 82.5%
  40 pip: 0.3542 -> +0.974, 80.8%
  (matches original: +1.37 ATR break-even context; still positive unless extreme)

Item 2 (bad ticks): 6 bars with range >12 ATR out of ~156k daily bars (0.004%).
  No trade in our candidate set touches any of these; negligible.

Item 3 (stop execution, daily bars only): 191 stop-touching trades.
  excursion past stop (ATR): median 0.378, p90 1.373, max 79.815
  50.3% close beyond stop; p90 lossR ~2.33 (vs -1.0 backtested)
  matches recorded (51.8% close beyond, p90 2.36) — the 48.2% "revival" was from a different population

Item 4 (walk-forward, 3-way): train<2023-09, valid<2025-01, test>=2025-01
  train (n=1194, 87%): E[R]=+1.324, win 83.4%
  valid (n=97, 7%):    E[R]=+1.328, win 80.4%
  test  (n=111, 8%):   E[R]=+1.375, win 88.3%
  No decay; test improves. Short-side w_pos<0.8 filter consistent.
"""

# generated for reference only
pass
