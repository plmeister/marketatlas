"""Day{N} filmstrip snapshot renderer for the paper tick.

Draws an annotated candlestick frame for one open paper trade: the bars from a
little before the entry pivot up to the day currently revealed, plus the entry,
stop and target levels. One frame per processed day builds a filmstrip whose
final frame carries the resolution status.

matplotlib (Agg) -> SVG, so the output is small, crisp and themeable. Fonts are
left as text (``svg.fonttype='none'``) so the file stays compact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_BULL = "#26a69a"
_BEAR = "#ef5350"
_ENTRY = "#2962ff"
_STOP = "#ef5350"
_TARGET = "#26a69a"
_PUBLISH = "#ffb300"


def render_day_snapshot(
    d: dict[str, Any],
    pos: dict[str, Any],
    day: int,
    status: str,
    out_path: str | Path,
    window: int = 40,
    signals: list[dict[str, Any]] | None = None,
) -> str:
    """Render one filmstrip frame for ``pos`` at ``day`` and save to ``out_path``.

    Parameters
    ----------
    d:
        cleaned symbol dict from ``data_loader.load`` (needs open/high/low/close,
        timestamp).
    pos:
        paper position dict (sym, publish_date, ci, entry, stop, target, dir).
    day:
        trading days elapsed since the entry bar (0 = publish/entry bar).
    status:
        short state label shown in the title: ``published`` / ``open`` /
        ``stop`` / ``target`` / ``timeout``.
    window:
        bars of pre-entry context to include.
    signals:
        optional strategy signal annotations. Each entry is a dict with ``i``
        (bar index), ``price``, ``kind`` (``"high"`` / ``"low"``) and optional
        ``style`` (``"muted"`` default / ``"trigger"``) and ``label``. This is
        deliberately generic so any strategy can surface its own markers.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    plt.rcParams["svg.fonttype"] = "none"

    o, h, lo, c = d["open"], d["high"], d["low"], d["close"]
    ci = int(pos["ci"])
    end = min(ci + int(day), len(c) - 1)
    start = max(0, ci - window)

    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=110)

    for k in range(start, end + 1):
        up = c[k] >= o[k]
        colour = _BULL if up else _BEAR
        ax.plot([k, k], [lo[k], h[k]], color=colour, linewidth=0.8, zorder=2, solid_capstyle="butt")
        body_lo = min(o[k], c[k])
        body_hi = max(o[k], c[k])
        height = max(body_hi - body_lo, (max(h[k] - lo[k], 1e-9)) * 0.006)
        ax.add_patch(Rectangle((k - 0.32, body_lo), 0.64, height, facecolor=colour,
                               edgecolor=colour, linewidth=0.4, zorder=3))

    entry, stop, target = float(pos["entry"]), float(pos["stop"]), float(pos["target"])
    ax.axhline(entry, color=_ENTRY, linewidth=1.0, zorder=4)
    ax.axhline(stop, color=_STOP, linewidth=1.0, linestyle="--", zorder=4)
    ax.axhline(target, color=_TARGET, linewidth=1.0, linestyle="--", zorder=4)
    # publish marker: the bar (and price) the trade was added on
    ax.axvline(ci, color=_PUBLISH, linewidth=1.3, zorder=5)
    ax.scatter([ci], [entry], marker="o", s=30, color=_PUBLISH,
               edgecolor="#263238", linewidth=0.7, zorder=6)
    ax.annotate("published", xy=(ci, 0.995), xycoords=("data", "axes fraction"),
                color=_PUBLISH, fontsize=8, fontweight="bold", va="top", ha="center", zorder=7)

    # strategy signals: swing pivots (muted) and the entry trigger (accent)
    sig_prices: list[float] = []
    for s in signals or []:
        i = int(s["i"])
        price = float(s["price"])
        if i < start or i > end:
            continue
        sig_prices.append(price)
        kind = s.get("kind", "low")
        accent = s.get("style") == "trigger"
        marker = "v" if kind == "high" else "^"
        base = _BEAR if kind == "high" else _BULL
        ax.scatter([i], [price], marker=marker, s=58 if accent else 26,
                   color=base, alpha=1.0 if accent else 0.55,
                   edgecolor="#263238", linewidth=0.7 if accent else 0.4, zorder=6)
        if s.get("label"):
            above = kind == "low"
            ax.annotate(s["label"], xy=(i, price),
                        xytext=(0, 12 if above else -14), textcoords="offset points",
                        color="#263238", fontsize=8, fontweight="bold",
                        ha="center", va="bottom" if above else "top", zorder=8)

    span = max(target, entry, stop) - min(target, entry, stop)
    if span <= 0:
        span = max(h[start : end + 1] + [entry]) - min(lo[start : end + 1] + [entry])
    pad = span * 0.08

    x_lbl = start - 0.5
    ax.annotate("entry", (x_lbl, entry), color=_ENTRY, fontsize=8, va="bottom", ha="left")
    ax.annotate("stop", (x_lbl, stop), color=_STOP, fontsize=8, va="bottom", ha="left")
    ax.annotate("target", (x_lbl, target), color=_TARGET, fontsize=8, va="bottom", ha="left")

    ax.set_xlim(start - 1, end + 1.5)
    y_lo = min(lo[start : end + 1] + [stop, entry, target] + sig_prices) - pad
    y_hi = max(h[start : end + 1] + [stop, entry, target] + sig_prices) + pad
    ax.set_ylim(y_lo, y_hi)

    # date ticks: show each trading day when small window, else sparse
    ts = d["timestamp"]
    span_bars = end - start + 1
    if span_bars <= 80:
        ticks = list(range(start, end + 1))
    else:
        nticks = 12
        step = max(1, (end - start) // nticks)
        ticks = list(range(start, end + 1, step))
    ticks = [t for t in ticks if t >= start and t <= end]
    ax.set_xticks(ticks)
    ax.set_xticklabels([ts[t].strftime("%m-%d") for t in ticks],
                        fontsize=7, rotation=60, ha="right")
    ax.tick_params(axis="y", labelsize=7)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    r_note = ""
    if pos.get("r") is not None:
        r_note = f"  r={float(pos['r']):+.2f}"
    title = f"{pos['sym']}  {pos['publish_date']}  day{day}  {status}{r_note}"
    ax.set_title(title, fontsize=11, loc="left")

    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="svg")
    plt.close(fig)
    return str(out_path)
