"""Trade-event message formatting and chart rendering.

Transport lives in matrix_transport.py (matrix-nio, E2EE). Keep this module
free of network concerns so it is easy to test and reuse.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _pip_factor(sym: str) -> float | None:
    if sym.startswith(("XAU", "XAG", "XPT", "XPD")):
        return None
    if sym.endswith("JPY"):
        return 0.01
    return 0.0001


def _dist(sym: str, entry: float, level: float) -> str:
    diff = level - entry
    factor = _pip_factor(sym)
    if factor is None:
        return f"{diff:+.5f}"
    return f"{diff / factor:+.0f} p"


def _direction_label(direction: int) -> str:
    return "LONG" if direction > 0 else "SHORT"


def format_entry(event: dict[str, Any]) -> str:
    sym = str(event["sym"])
    direction = int(event["dir"])
    entry = float(event["entry"])
    stop = float(event["stop"])
    target = float(event["target"])
    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = reward / risk if risk else 0.0
    return "\n".join(
        [
            f"\U0001f7e2 ENTRY  {sym}  {_direction_label(direction)}",
            f"  entry  {entry:.5f}",
            f"  stop   {stop:.5f}   {_dist(sym, entry, stop)}",
            f"  target {target:.5f}   {_dist(sym, entry, target)}   R:R 1:{rr:.1f}",
            f"  signal bar {event['date']} (D1)",
        ]
    )


def format_exit(event: dict[str, Any]) -> str:
    sym = str(event["sym"])
    direction = int(event["dir"])
    reason = str(event.get("reason", "?"))
    r = float(event.get("r", 0.0))
    r_net = float(event.get("r_net", 0.0))
    capital = event.get("capital")
    tail = f"  capital {float(capital):.2f}" if capital is not None else ""
    return (
        f"\U0001f534 EXIT  {sym}  {_direction_label(direction)} -> {reason}\n"
        f"  {r:+.2f}R (net {r_net:+.2f}R){tail}"
    )


_CHART_WIDTH = 10.0
_CHART_HEIGHT = 5.6
_CHART_DPI = 110


def _study_candles(sym: str, tf: str = "1d") -> list[dict[str, Any]]:
    from data_loader import load

    d = load(sym, tf)
    ts, o, h, low, c = (d[k] for k in ("timestamp", "open", "high", "low", "close"))
    return [
        {"ts": ts[i].isoformat(), "o": o[i], "h": h[i], "l": low[i], "c": c[i], "v": 0.0}
        for i in range(len(ts))
    ]


def render_entry_chart(
    sym: str, event: dict[str, Any], out_path: Path, bars: int = 60
) -> tuple[int, int]:
    """Render the standard dark TradingView-style candle snapshot for an entry.

    Reuses ``marketatlas.visualization.snapshot.render_trade_snapshot`` so the
    alert image matches the production charts: dark palette, candles and the
    translucent stop/target panes around the entry. Candles are truncated to the
    signal bar so the frame carries no lookahead.
    """
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from marketatlas.visualization.snapshot import render_trade_snapshot

    date = str(event["date"])
    poi = datetime.fromisoformat(date).replace(tzinfo=UTC)
    candles = [c for c in _study_candles(sym) if c["ts"][:10] <= date]
    if not candles:
        raise ValueError(f"no candles for {sym} up to {date}")

    source = SimpleNamespace(
        symbol=sym,
        timeframe="1d",
        timeframes=("1d",),
        candles={"1d": candles},
        frames=(),
    )

    entry = float(event["entry"])
    stop = float(event["stop"])
    target = float(event["target"])
    risk = abs(entry - stop)
    rr = abs(target - entry) / risk if risk else None
    direction = "long" if int(event["dir"]) > 0 else "short"

    render_trade_snapshot(
        source,
        poi,
        out_path,
        entry=entry,
        stop=stop,
        target=target,
        rr_ratio=rr,
        submit_ts=poi,
        direction=direction,
        pre=bars,
        post=0,
        width=_CHART_WIDTH,
        height=_CHART_HEIGHT,
        show_volume=False,
    )
    return int(_CHART_WIDTH * _CHART_DPI), int(_CHART_HEIGHT * _CHART_DPI)
