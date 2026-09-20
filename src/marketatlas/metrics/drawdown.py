"""Equity-curve drawdown engine (backlog 100).

Operates on a chronological ``(timestamp, balance)`` series and reports more
than the worst peak-to-trough: every drawdown episode's depth, dates, duration
in bars, and recovery time. Extends ``TradeLedger.max_drawdown`` (realized-P&L
only, no dates/durations) to the full time series. Pure functions, no I/O —
the output dict is JSON-serializable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DrawdownEpisode:
    """One peak-to-trough (to-recovery) episode, indices into the input series."""

    depth_pct: float
    depth_abs: float
    peak_ts: datetime
    peak_balance: float
    trough_ts: datetime
    trough_balance: float
    peak_idx: int
    trough_idx: int
    recovery_idx: int | None  # None → still underwater at series end


def _episode_dict(ep: DrawdownEpisode) -> dict[str, object]:
    return {
        "depth_pct": ep.depth_pct,
        "depth_abs": ep.depth_abs,
        "peak": {"t": ep.peak_ts.isoformat(), "balance": ep.peak_balance},
        "trough": {"t": ep.trough_ts.isoformat(), "balance": ep.trough_balance},
        "duration_bars": max(0, ep.trough_idx - ep.peak_idx),
        "recovery_bars": (
            max(0, ep.recovery_idx - ep.trough_idx) if ep.recovery_idx is not None else None
        ),
        "recovered": ep.recovery_idx is not None,
    }


def drawdown_analysis(points: list[tuple[datetime, float]]) -> dict[str, object]:
    """Measure drawdown episodes over an ordered ``(ts, balance)`` series.

    The series should include the starting point (initial balance before any
    trade) so a trough that bottoms below the start is still a real episode.
    ``points = []`` yields a zeroed dashboard; a flat or monotonically rising
    series reports no episodes and ``max_drawdown_pct = 0.0``.

    Durations are in *bars* (series points spanned): ``duration_bars`` counts
    points from the episode's peak bar to its trough bar; ``recovery_bars``
    counts "bars" from the trough back to (and including) the first bar that
    reclaims the old peak. An episode still underwater at the end reports
    ``recovered=False`` and ``recovery_bars=None``.
    """
    if not points:
        return _empty()

    episodes: list[DrawdownEpisode] = []
    peak_idx = 0
    peak_ts, peak_balance = points[0]
    trough_balance: float | None = None
    trough_ts: datetime | None = None
    trough_idx = 0

    for i, (ts, balance) in enumerate(points):
        if balance >= peak_balance:
            if trough_balance is not None and trough_ts is not None:
                episodes.append(
                    DrawdownEpisode(
                        depth_pct=_depth_pct(peak_balance, trough_balance),
                        depth_abs=peak_balance - trough_balance,
                        peak_ts=peak_ts,
                        peak_balance=peak_balance,
                        trough_ts=trough_ts,
                        trough_balance=trough_balance,
                        peak_idx=peak_idx,
                        trough_idx=trough_idx,
                        recovery_idx=i,
                    )
                )
                trough_balance = None
                trough_ts = None
            peak_ts, peak_balance = ts, balance
            peak_idx = i
        elif trough_balance is None or balance < trough_balance:
            trough_ts, trough_balance = ts, balance
            trough_idx = i

    if trough_balance is not None and trough_ts is not None:
        episodes.append(
            DrawdownEpisode(
                depth_pct=_depth_pct(peak_balance, trough_balance),
                depth_abs=peak_balance - trough_balance,
                peak_ts=peak_ts,
                peak_balance=peak_balance,
                trough_ts=trough_ts,
                trough_balance=trough_balance,
                peak_idx=peak_idx,
                trough_idx=trough_idx,
                recovery_idx=None,
            )
        )

    if not episodes:
        return _empty(start=(points[0][0], points[0][1]))

    worse = max(episodes, key=lambda e: e.depth_pct)
    durations = [e.trough_idx - e.peak_idx for e in episodes]
    recoveries = [e.recovery_idx - e.trough_idx for e in episodes if e.recovery_idx is not None]
    depths = [e.depth_pct for e in episodes]
    return {
        "count": len(episodes),
        "max_drawdown_pct": worse.depth_pct,
        "max_drawdown_abs": worse.depth_abs,
        "peak": {"t": worse.peak_ts.isoformat(), "balance": worse.peak_balance},
        "trough": {"t": worse.trough_ts.isoformat(), "balance": worse.trough_balance},
        "duration_bars": worse.trough_idx - worse.peak_idx,
        "recovery_bars": (
            worse.recovery_idx - worse.trough_idx if worse.recovery_idx is not None else None
        ),
        "recovered": worse.recovery_idx is not None,
        "avg_drawdown_pct": sum(depths) / len(depths) if depths else 0.0,
        "avg_duration_bars": sum(durations) / len(durations) if durations else 0.0,
        "max_recovery_bars": max(recoveries) if recoveries else None,
        "episodes": [_episode_dict(e) for e in episodes],
    }


def _depth_pct(peak: float, trough: float) -> float:
    return (peak - trough) / peak * 100.0 if peak > 0.0 else 0.0


def _empty(start: tuple[datetime, float] | None = None) -> dict[str, object]:
    peak = {"t": start[0].isoformat(), "balance": start[1]} if start else None
    return {
        "count": 0,
        "max_drawdown_pct": 0.0,
        "max_drawdown_abs": 0.0,
        "peak": peak,
        "trough": None,
        "duration_bars": 0,
        "recovery_bars": None,
        "recovered": True,
        "avg_drawdown_pct": 0.0,
        "avg_duration_bars": 0.0,
        "max_recovery_bars": None,
        "episodes": [],
    }


def drawdown_distribution(
    episodes: list[dict[str, object]],
    thresholds: tuple[float, ...] = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0),
) -> dict[str, float]:
    """Empirical probability (from observed episodes) of exceeding depth thresholds.

    Heuristic risk-of-ruin / probability-of-substantial-loss estimate: the
    share of recorded drawdown episodes deeper than each threshold (pct). 0 for
    every threshold when no episodes exist. A heuristic, not a Monte-Carlo
    probability (the rigorous version lives in backlog 102).
    """
    depths = [
        d
        for e in episodes
        if isinstance((d := e.get("depth_pct")), int | float) and d >= 0.0
    ]
    return {
        f"gt_{int(t):d}pct": sum(1 for d in depths if d > t) / len(depths) if depths else 0.0
        for t in thresholds
    }
