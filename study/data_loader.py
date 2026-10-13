"""Load and clean the refetched Dukascopy study history.

Clean rules (as established before the /tmp wipe — see WORKLOG 2026-10-06):
- drop dead Saturday bars (zero-range artifacts that deflate SMA-ATR ~2.6%)
- clamp out-of-bounds OHLC bars (NZDJPY has 2)

Run: poetry run python study/audit.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

DATA = Path(__file__).resolve().parent.parent / "data" / "study"


def load(symbol: str, timeframe: str = "1d", clean: bool = True) -> dict[str, Any]:
    table = pq.read_table(DATA / f"{symbol}.{timeframe}.parquet")
    col = {name: table.column(name).to_pylist() for name in table.column_names}
    n = len(col["timestamp"])
    keep = [True] * n
    if clean:
        for i, ts in enumerate(col["timestamp"]):
            if ts.weekday() == 5:
                keep[i] = False
        # collapse same-date bars: the metals feed appends a tz-shifted
        # (04:00/05:00) duplicate alongside the historical 00:00 bar.
        seen: dict[Any, int] = {}
        for i, ts in enumerate(col["timestamp"]):
            if not keep[i]:
                continue
            j = seen.get(ts.date())
            if j is None:
                seen[ts.date()] = i
                continue
            if col["timestamp"][j].hour != 0 and ts.hour == 0:
                seen[ts.date()] = i
                keep[j] = False
            else:
                keep[i] = False
    out: dict[str, Any] = {}
    for name, values in col.items():
        if name == "volume":
            continue
        picked = [v for v, k in zip(values, keep, strict=True) if k]
        out[name] = picked
    if clean:
        for i in range(len(out["close"])):
            o, h, l, c = (out[k][i] for k in ("open", "high", "low", "close"))
            hi, lo = max(o, h, l, c), min(o, h, l, c)
            if h != hi or l != lo:
                out["high"][i], out["low"][i] = hi, lo
    out["_sym"] = symbol
    return out


def sma_atr(d: dict[str, Any], period: int = 14) -> list[float]:
    """Pivot-bar ATR used by the signal: rolling SMA of true range."""
    h, l, c = d["high"], d["low"], d["close"]
    trs = [0.0] * len(c)
    for i in range(1, len(c)):
        trs[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = [0.0] * len(c)
    run = 0.0
    for i in range(1, len(c)):
        run += trs[i]
        if i > period:
            run -= trs[i - period]
        atr[i] = run / min(i, period)
    return atr
