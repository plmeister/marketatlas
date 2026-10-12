#!/usr/bin/env python3
"""Stateful EOD paper-trading tick.

Replays the causal k=3.5 mean-reversion candidate one daily bar at a time:

* **publish** - on each processed date, any instrument whose entry close lands on
  that date is published as an open position (canonical id ``{SYM}_{date}``) and
  written to ``trades.jsonl``.
* **advance** - every open position is moved forward one revealed bar; stop/target
  are checked stop-first, then a ``HORIZON``-bar market close resolves a
  ``timeout``.
* **snapshots** - one annotated SVG frame per open position per day forms a
  ``day{N}`` filmstrip under ``<state>/snapshots``.

Point-in-time by construction: only bars at or after the entry bar are ever
examined, so a live run sees exactly what the historical replay sees.

Env:
    PAPER_TAG   log/state tag (default ``paper-test-v1-causal``)
    PAPER_ASOF  replay a single ``YYYY-MM-DD`` date instead of the whole window
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "study"))

import json  # noqa: E402
import statistics as st  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from datetime import UTC, date, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from data_loader import load  # noqa: E402
from execution import sim_base  # noqa: E402
from execution_causal import build_prod_causal  # noqa: E402
from paper_render import render_day_snapshot  # noqa: E402
from signal_check import weekly_context  # noqa: E402

SYMS = [
    "AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADJPY",
    "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD",
    "GBPAUD", "GBPJPY", "GBPNZD", "GBPUSD",
    "NZDCAD", "NZDJPY", "NZDUSD", "USDCAD", "USDCHF",
    "XAGUSD", "XAUUSD",
]
STOP_ATR = 1.5
TP_ATR = 3.0
HORIZON = 15
SHORT_WPOS_THR = 0.8
RISK_PCT = 1.0


class _Data:
    """Cached symbol frames + ``date -> bar index`` maps."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[dict[str, Any], dict[date, int]]] = {}

    def get(self, sym: str) -> tuple[dict[str, Any], dict[date, int]]:
        if sym not in self._cache:
            d = load(sym)
            idx = {ts.date(): i for i, ts in enumerate(d["timestamp"])}
            self._cache[sym] = (d, idx)
        return self._cache[sym]

    def weekly(self, sym: str) -> dict[str, Any]:
        return load(sym, "1w")


def _cost_r(data: _Data) -> float:
    """Flat round-trip spread cost expressed in R units (median ATR/price)."""
    try:
        atrp: list[float] = []
        for s in SYMS:
            d, _ = data.get(s)
            if len(d["close"]) < 100:
                continue
            wc = weekly_context(d, data.weekly(s))
            lg, atr = build_prod_causal(d)
            for t in sim_base(d, lg, atr, wc):
                if t["atr"] > 0 and t["entry"]:
                    atrp.append(t["atr"] / t["entry"])
        mf = st.median(atrp) if atrp else 0.001
        return 0.0010 / (1.5 * mf)
    except Exception:
        return 0.089


def _all_trades(data: _Data) -> dict[str, dict[str, Any]]:
    """Per-symbol strategy output: candidate trades plus the swing pivots and
    ATR series they were derived from (kept for chart annotation)."""
    out: dict[str, dict[str, Any]] = {}
    for s in SYMS:
        d, _ = data.get(s)
        if len(d["close"]) < 100:
            continue
        wc = weekly_context(d, data.weekly(s))
        lg, atr = build_prod_causal(d)
        out[s] = {
            "trades": sim_base(d, lg, atr, wc, thr=SHORT_WPOS_THR),
            "pivots": lg,
            "atr": atr,
        }
    return out


def _signals(sym: str, pos: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Chart annotations for one position: swing pivots plus the entry trigger.

    Only pivots at or before the last revealed bar are emitted, preserving the
    point-in-time property. The trigger is the pivot two bars before entry
    (``ci - 2``); its label carries the swing magnitude in ATR.
    """
    rec = ctx["trades"].get(sym)
    if not rec:
        return []
    pivots: list[tuple[int, str, float]] = rec["pivots"]
    atr = rec["atr"]
    ci = int(pos["ci"])
    end_idx = int(pos["cursor"])
    lo_i = max(0, ci - 40)

    trig_k = next((k for k, p in enumerate(pivots) if p[0] == ci - 2), None)
    label = None
    if trig_k is not None:
        ni, typ, price = pivots[trig_k]
        a = atr[ni] if ni < len(atr) else atr[-1]
        kind = "low" if typ == "L" else "high"
        label = f"{kind} swing"
        if trig_k > 0 and a > 0:
            mag = abs(price - pivots[trig_k - 1][2]) / a
            label = f"{kind} swing  {mag:.1f}×ATR"

    anns: list[dict[str, Any]] = []
    for k, (i, typ, price) in enumerate(pivots):
        if i < lo_i or i > end_idx:
            continue
        anns.append({
            "i": i,
            "price": float(price),
            "kind": "low" if typ == "L" else "high",
            "style": "trigger" if k == trig_k else "muted",
            "label": label if k == trig_k else None,
        })
    return anns


def daterange(s: date, e: date) -> Iterator[date]:
    cur = s
    while cur < e:
        yield cur
        cur += timedelta(days=1)


def _load_published(trades_path: Path) -> set[str]:
    ids: set[str] = set()
    if trades_path.exists():
        for line in trades_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                continue
    return ids


def _event(events_path: Path, payload: dict[str, Any]) -> None:
    with open(events_path, "a") as f:
        f.write(json.dumps(payload) + "\n")


def _snap_path(snap_dir: Path, pos: dict[str, Any]) -> Path:
    return snap_dir / f"{pos['id']}_day{pos['day']}.svg"


def _advance(
    pos: dict[str, Any],
    d: dict[str, Any],
    idx: int,
) -> tuple[str, float] | None:
    """Reveal bars up to ``idx``; return (status, exit_price) if resolved."""
    h, lo, c = d["high"], d["low"], d["close"]
    direction = pos["dir"]
    j = pos["cursor"] + 1
    while j <= idx:
        if direction > 0:
            if lo[j] <= pos["stop"]:
                pos["cursor"] = j
                return "stop", pos["stop"]
            if h[j] >= pos["target"]:
                pos["cursor"] = j
                return "target", pos["target"]
        else:
            if h[j] >= pos["stop"]:
                pos["cursor"] = j
                return "stop", pos["stop"]
            if lo[j] <= pos["target"]:
                pos["cursor"] = j
                return "target", pos["target"]
        j += 1
    pos["cursor"] = idx
    if idx - pos["ci"] >= HORIZON:
        return "timeout", c[idx]
    return None


def process_day(proc_date: date, state: dict[str, Any], ctx: dict[str, Any]) -> None:
    data: _Data = ctx["data"]
    events_path: Path = ctx["events_path"]
    snap_dir: Path = ctx["snap_dir"]
    trades_path: Path = ctx["trades_path"]
    cost: float = ctx["cost"]

    # 1. advance open positions through this bar
    for pos in list(state["open_positions"]):
        d, idxmap = data.get(pos["sym"])
        idx = idxmap.get(proc_date)
        if idx is None or idx <= pos["cursor"]:
            continue
        resolved = _advance(pos, d, idx)
        pos["day"] = idx - pos["ci"]
        if resolved is None:
            render_day_snapshot(d, pos, pos["day"], "open", _snap_path(snap_dir, pos),
                                signals=_signals(pos["sym"], pos, ctx))
            _event(events_path, {
                "type": "frame", "id": pos["id"], "day": pos["day"], "status": "open",
            })
            continue
        status, exit_px = resolved
        r = pos["dir"] * (exit_px - pos["entry"]) / (STOP_ATR * pos["atr"])
        net = r - cost
        state["capital"] *= 1.0 + (RISK_PCT / 100.0) * net
        pos["status"] = status
        pos["r"] = r
        pos["exit"] = exit_px
        pos["exit_date"] = proc_date.isoformat()
        render_day_snapshot(d, pos, pos["day"], status, _snap_path(snap_dir, pos),
                            signals=_signals(pos["sym"], pos, ctx))
        _event(events_path, {
            "type": "resolve", "id": pos["id"], "status": status,
            "r": round(r, 4), "capital": round(state["capital"], 4),
        })
        state["open_positions"].remove(pos)
        if state["capital"] > state["peak"]:
            state["peak"] = state["capital"]
        dd = (state["peak"] - state["capital"]) / state["peak"] if state["peak"] else 0.0
        state["maxdd"] = max(state["maxdd"], dd)

    # 2. publish trades whose entry close lands on this date
    for sym in SYMS:
        for t in ctx["trades"].get(sym, {}).get("trades", []):
            if t["date"].date() != proc_date:
                continue
            tid = f"{sym}_{proc_date.isoformat()}"
            if tid in ctx["published"]:
                continue
            if any(p["sym"] == sym for p in state["open_positions"]):
                continue
            direction = int(t["dir"])
            pos = {
                "id": tid,
                "sym": sym,
                "publish_date": proc_date.isoformat(),
                "ci": int(t["ci"]),
                "cursor": int(t["ci"]),
                "day": 0,
                "entry": float(t["entry"]),
                "stop": float(t["entry"]) - direction * STOP_ATR * float(t["atr"]),
                "target": float(t["entry"]) + direction * TP_ATR * float(t["atr"]),
                "atr": float(t["atr"]),
                "dir": direction,
                "status": "published",
                "r": None,
            }
            state["open_positions"].append(pos)
            state["trade_count"] = state.get("trade_count", 0) + 1
            ctx["published"].add(tid)
            d, _ = data.get(sym)
            with open(trades_path, "a") as f:
                f.write(json.dumps({
                    "id": tid, "sym": sym, "dir": direction,
                    "publish_date": proc_date.isoformat(),
                    "entry": pos["entry"], "stop": pos["stop"], "target": pos["target"],
                    "atr": pos["atr"],
                }) + "\n")
            render_day_snapshot(d, pos, 0, "published", _snap_path(snap_dir, pos),
                                signals=_signals(sym, pos, ctx))
            _event(events_path, {
                "type": "publish", "id": tid, "date": proc_date.isoformat(),
                "sym": sym, "dir": direction,
            })

    _event(events_path, {"type": "tick", "date": proc_date.isoformat()})


def _new_state() -> dict[str, Any]:
    return {
        "capital": 100.0,
        "peak": 100.0,
        "maxdd": 0.0,
        "last_processed": None,
        "open_positions": [],
        "trade_count": 0,
    }


def main() -> None:
    tag = os.environ.get("PAPER_TAG", "paper-test-v1-causal")
    state_dir = Path(os.path.expanduser("~/.local/share/marketatlas/paper-logs")) / tag
    state_dir.mkdir(parents=True, exist_ok=True)
    snap_dir = state_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "state.json"
    events_path = state_dir / "events.jsonl"
    trades_path = state_dir / "trades.jsonl"

    if state_path.exists():
        state = json.loads(state_path.read_text())
        state.setdefault("open_positions", [])
        state.setdefault("trade_count", 0)
    else:
        state = _new_state()

    data = _Data()
    ctx: dict[str, Any] = {
        "data": data,
        "cost": _cost_r(data),
        "trades": _all_trades(data),
        "published": _load_published(trades_path),
        "snap_dir": snap_dir,
        "events_path": events_path,
        "trades_path": trades_path,
    }

    asof = os.environ.get("PAPER_ASOF")
    if asof:
        process_day(date.fromisoformat(asof), state, ctx)
    else:
        now_dt = datetime.now(UTC)
        today = now_dt.date()
        last_str = state.get("last_processed")
        last = date.fromisoformat(last_str) if last_str else today - timedelta(days=7)
        if last >= today:
            _event(events_path, {"type": "heartbeat", "ts": now_dt.isoformat()})
        else:
            for proc_date in daterange(last + timedelta(days=1), today):
                process_day(proc_date, state, ctx)
            state["last_processed"] = today.isoformat()

    state_path.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
