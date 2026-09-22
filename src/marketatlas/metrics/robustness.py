"""Backtest robustness layer (backlog 102).

Metrics 099-101 hand out point estimates: a CAGR, an expectancy, a max
drawdown. Point estimates fool people — a CAGR that doubles yearly can be a
single lucky month. This module wraps the realized trade sequence in
re-sampling so the variance around every headline number is visible, and adds
out-of-sample/walk-forward splits so edge is judged on unseen data.

Two Monte-Carlo treatments are provided (the backlog calls them
"shuffle" and "variation of individual trade outcomes"):

* ``mode="shuffle"`` — permutes the *order* of the realized R sequence and
  compounds it into an equity path. The endpoint (total CAGR) is
  order-independent, but the *path* is not: this yields the distribution of
  drawdowns and the worst-case-plausible band that a different sequencing of
  the same trades would have shown.
* ``mode="resample"`` (default) — draws realized R values **with replacement**
  (bootstrap of the outcome distribution), so both CAGR and expectancy get a
  real distribution, plus the probability that a compounded account ends
  negative over 1/3/5-year horizons.

Both compound each simulated trade at a fixed ``risk_fraction`` of the running
balance (``mean risk_amount / initial_balance`` when not given) — the equity
curve model the tradebook actually produces. Everything is seeded for
reproducibility and JSON-serializable; no I/O.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from marketatlas.metrics import drawdown, stats

Trade = Mapping[str, Any]

DECIDED = ("win", "loss")
_HORIZONS: tuple[float, ...] = (1.0, 3.0, 5.0)
_DEFAULT_RISK_FRACTION = 0.01
# Compounded growth stays finite: clamp log-balance inside float range and
# clamp the per-trade risk fraction so a single sampled R cannot bankrupt the
# path in a way that explodes the arithmetic.
_LOG_FLOOR = -709.0
_LOG_CEIL = 709.0

_MC_PERCS = {
    name: value for name, value in ((f"p{int(v)}", v / 100.0) for v in (5, 25, 50, 75, 95))
}


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        f = float(value)
        return f if math.isfinite(f) else None
    return None


def _ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _naive(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _r(trade: Trade) -> float | None:
    return _float(trade.get("r_multiple"))


def _num(value: Any) -> float | None:
    return _float(value)


def _gap(a: Any, b: Any) -> float | None:
    """Signed ``a - b`` over numeric look-a-likes; ``None`` when either is missing."""
    fa, fb = _num(a), _num(b)
    return (fa - fb) if fa is not None and fb is not None else None


def _foos(fold: Mapping[str, object] | None) -> Mapping[str, object]:
    if not isinstance(fold, Mapping):
        return {}
    oos = fold.get("out_of_sample")
    return oos if isinstance(oos, Mapping) else {}


def _decided(trades: Sequence[Trade]) -> list[Trade]:
    """Decided (win/loss) trades with an R value and a resolution timestamp."""
    out: list[Trade] = []
    for t in trades:
        if t.get("result") not in DECIDED:
            continue
        r = _r(t)
        ts = _ts(t.get("exit_ts"))
        if r is None or ts is None:
            continue
        out.append(t)
    return out


def _ordered(trades: Sequence[Trade]) -> list[Trade]:
    return sorted(_decided(trades), key=lambda t: _naive(_ts(t.get("exit_ts")) or datetime.min))


def _years(trades: Sequence[Trade]) -> float | None:
    """Calendar span (years) from the first to the last resolved trade."""
    stamps = [_naive(_ts(t.get("exit_ts")) or datetime.min) for t in trades]
    if len(stamps) < 2:
        return None
    days = max(0.0, (max(stamps) - min(stamps)).total_seconds() / 86400.0)
    return days / 365.25


def _resolve_initial(trades: Sequence[Trade], initial_balance: float | None) -> float:
    """Explicit balance, else the portfolio default 100.0 index convention."""
    if initial_balance is not None:
        return float(initial_balance)
    return 100.0


def _resolve_risk_fraction(
    trades: Sequence[Trade], initial: float, risk_fraction: float | None
) -> float:
    if risk_fraction is not None:
        value = float(risk_fraction)
    else:
        risks = [
            r for t in _decided(trades) if (r := _float(t.get("risk_amount"))) is not None and r > 0
        ]
        value = sum(risks) / len(risks) / initial if risks and initial > 0 else 0.0
    if not math.isfinite(value) or value <= 0.0:
        return _DEFAULT_RISK_FRACTION
    return min(value, 0.5)


def _log_growth(r: float, f: float) -> float:
    """Log growth factor for a sampled R at risk fraction ``f`` (ruin → -inf)."""
    g = 1.0 + f * r
    if g <= 0.0:
        return -math.inf
    return math.log(g)


def _compounded_progress(rs: Sequence[float], f: float, initial: float) -> list[float]:
    """Balance path from compounding ``rs`` at fraction ``f`` (log-space)."""
    path = [float(initial)]
    log_bal = math.log(max(float(initial), 1e-9))
    for r in rs:
        log_bal += _log_growth(float(r), f)
        log_bal = min(max(log_bal, _LOG_FLOOR), _LOG_CEIL)
        path.append(math.exp(log_bal))
    return path


def _path_drawdown(ts: Sequence[datetime], balances: Sequence[float]) -> float:
    points = list(zip(ts, balances))
    dd = drawdown.drawdown_analysis(points)
    value = dd.get("max_drawdown_pct")
    return float(value) if isinstance(value, int | float) else 0.0


def _percentile_distribution(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {name: None for name in _MC_PERCS}
    ps = stats.percentiles(values, _MC_PERCS)
    return {name: (round(v, 8) if v is not None else None) for name, v in dict(ps).items()}


def _neg_return_probabilities(
    rng: random.Random,
    rs: Sequence[float],
    trades_per_year: float,
    f: float,
    n_sims: int,
    horizons: Sequence[float],
) -> dict[str, float]:
    """P(compounded account turns negative) over each horizon, bootstrap-style."""
    horizons = tuple(horizons) or _HORIZONS
    out: dict[str, float] = {}
    per_trade_neg = sum(1 for r in rs if r < 0) / len(rs) if rs else 0.0
    out["per_trade"] = per_trade_neg
    out["trades_per_year"] = trades_per_year
    n = len(rs)
    for h in horizons:
        n_h = max(1, round(h * trades_per_year))
        neg = 0
        for _ in range(n_sims):
            total = 0.0
            for _ in range(n_h):
                total += _log_growth(rng.choice(rs), f) if n else -math.inf
            if total < 0.0:
                neg += 1
        out[f"{h:g}y"] = neg / n_sims
    return out


def _sim_stats(
    rs: Sequence[float], ts: Sequence[datetime], f: float, initial: float, years: float | None
) -> dict[str, float | None]:
    path = _compounded_progress(rs, f, initial)
    final = path[-1]
    dd = _path_drawdown(ts, path)
    total_return = (final / initial - 1.0) if initial > 0 else None
    cagr = stats.cagr(final, initial, years) if years else None
    expectancy = stats.mean([float(r) for r in rs])
    return {
        "final": final,
        "cagr": cagr,
        "total_return": total_return,
        "max_drawdown_pct": dd,
        "expectancy": expectancy,
    }


def _aggregate(rows: list[dict[str, float | None]], key: str) -> dict[str, float | None]:
    vals = sorted(v for r in rows if (v := r.get(key)) is not None and math.isfinite(v))
    if not vals:
        return {name: None for name in _MC_PERCS}
    return _percentile_distribution(vals)


def monte_carlo(
    trades: Sequence[Trade],
    *,
    n_sims: int = 1000,
    seed: int = 42,
    mode: str = "resample",
    initial_balance: float | None = None,
    risk_fraction: float | None = None,
    horizons_years: Sequence[float] = _HORIZONS,
) -> dict[str, object]:
    """Monte-Carlo re-sampling of the realized trade sequence.

    ``mode`` shakes the estimate in two complementary ways:

    * ``"resample"`` (default) — bootstrap each simulated book from the R
      distribution, giving a genuine distribution of CAGR / expectancy /
      total return and horizon risk.
    * ``"shuffle"`` — permute the realized order only; total return is fixed
      by construction, so the value is the *drawdown* band of every possible
      sequencing of the same trades.

    Trade outcomes compound at ``risk_fraction`` of the running balance
    (estimated from ``mean(risk_amount)/initial_balance`` when omitted).
    Seeded (``random.Random(seed)``) so identical inputs give identical output.
    """
    if mode not in ("resample", "shuffle"):
        raise ValueError("mode must be 'resample' (bootstrap outcomes) or 'shuffle' (reorder)")
    if n_sims < 1:
        raise ValueError("n_sims must be >= 1")
    decided = _ordered(trades)
    rs = [float(_r(t) or 0.0) for t in decided]
    ts = [_naive(_ts(t.get("exit_ts")) or datetime.min) for t in decided]
    initial = _resolve_initial(trades, initial_balance)
    f = _resolve_risk_fraction(trades, initial, risk_fraction)
    years = _years(decided)
    tpy = (len(rs) / years) if years and years > 0 else 0.0

    rng = random.Random(seed)
    rows: list[dict[str, float | None]] = []
    for _ in range(n_sims):
        sampled = rng.choices(rs, k=len(rs)) if mode == "resample" else rng.sample(rs, len(rs))
        rows.append(_sim_stats(sampled, ts, f, initial, years))

    mc: dict[str, dict[str, float | None]] = {}
    for key in ("cagr", "total_return", "max_drawdown_pct", "expectancy"):
        mc[key] = _aggregate(rows, key)

    neg_prob: dict[str, float] = {}
    if mode == "resample" and tpy > 0:
        neg_prob = _neg_return_probabilities(rng, rs, tpy, f, n_sims, tuple(horizons_years))

    observed = _sim_stats(rs, ts, f, initial, years)  # unshuffled realization
    return {
        "mode": mode,
        "n_sims": n_sims,
        "seed": seed,
        "trades_used": len(rs),
        "years": years,
        "trade_frequency_per_year": tpy,
        "initial_balance": initial,
        "risk_fraction": f,
        "observed": {
            "cagr_pct": observed["cagr"] * 100 if observed["cagr"] is not None else None,
            "total_return_pct": (
                observed["total_return"] * 100 if observed["total_return"] is not None else None
            ),
            "max_drawdown_pct": observed["max_drawdown_pct"],
            "expectancy_r": observed["expectancy"],
        },
        "confidence_intervals": mc,
        "worst_case_drawdown": {
            "p50_pct": mc["max_drawdown_pct"]["p50"],
            "p95_pct": mc["max_drawdown_pct"]["p95"],
            "p99_note": (
                "p99 approximated by the observed 95th percentile band; "
                "see confidence_intervals"
            ),
        },
        "negative_return_probability": neg_prob,
        "note": (
            "compounds each trade at a fixed risk fraction of the running "
            "balance; 'shuffle' keeps the total return fixed and reports the "
            "possible drawdown paths. Seeded — reproducible."
        ),
    }


def _period_metrics(
    trades: Sequence[Trade],
    initial_balance: float,
    timeframe: str | None = None,
    periods_per_year: float | None = None,
) -> dict[str, object]:
    from marketatlas.metrics.portfolio import portfolio_metrics
    from marketatlas.metrics.trades import trade_metrics

    tm = trade_metrics(trades)
    pm = portfolio_metrics(trades, None, initial_balance, timeframe, periods_per_year)
    pm_ret = pm["returns"]
    pm_sum = pm["summary"]
    assert isinstance(pm_ret, dict) and isinstance(pm_sum, dict)
    tm_exp = tm["expectancy"]
    tm_wr = tm["win_rate"]
    tm_pf = tm["profit_factor"]
    assert isinstance(tm_exp, dict) and isinstance(tm_wr, dict) and isinstance(tm_pf, dict)
    return {
        "count": len(trades),
        "cagr_pct": pm_ret.get("cagr_pct"),
        "total_return_pct": pm_sum.get("total_return_pct"),
        "expectancy_r": tm_exp.get("expectancy_r"),
        "win_rate": tm_wr.get("decided"),
        "profit_factor_r": tm_pf.get("profit_factor_r"),
    }


def out_of_sample_split(
    trades: Sequence[Trade],
    *,
    test_fraction: float = 0.3,
    initial_balance: float | None = None,
    timeframe: str | None = None,
    periods_per_year: float | None = None,
) -> dict[str, object]:
    """In-sample vs out-of-sample metrics over a chronological split.

    Trades ordered by exit time; the first ``1 - test_fraction`` are the
    training (in-sample) block, the tail is held out. Each block is evaluated
    against its *own* reconstructed starting balance (test start = running
    balance at the split boundary) so the gap is not distorted by the shared
    baseline. No trade lands in both blocks — leak-free by construction.
    """
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be in (0, 1)")
    ordered = [
        t
        for t in sorted(trades, key=lambda t: _naive(_ts(t.get("exit_ts")) or datetime.min))
        if _ts(t.get("exit_ts")) is not None
    ]
    if not ordered:
        return {"count": 0, "note": "no trades to split"}
    split_idx = int((1.0 - test_fraction) * len(ordered)) or 1
    train = ordered[:split_idx]
    test = ordered[split_idx:]
    init = _resolve_initial(trades, initial_balance)
    train_initial = init
    test_initial = init + sum(_float(t.get("pnl")) or 0.0 for t in train)
    train_m = _period_metrics(train, train_initial, timeframe, periods_per_year)
    test_m = _period_metrics(test, test_initial, timeframe, periods_per_year)

    gaps: dict[str, float | None] = {}
    for key in ("cagr_pct", "total_return_pct", "expectancy_r", "win_rate", "profit_factor_r"):
        a = train_m.get(key)
        b = test_m.get(key)
        gaps[f"{key}_gap"] = (b - a) if a is not None and b is not None else None  # type: ignore[operator]

    return {
        "count": len(ordered),
        "train_count": len(train),
        "test_count": len(test),
        "test_fraction": test_fraction,
        "split_at": test[0].get("exit_ts") if test else None,
        "in_sample": train_m,
        "out_of_sample": test_m,
        "gap": gaps,
        "leakage_check": {
            "disjoint": True,
            "note": "train/test share no trades (chronological split)",
        },
    }


def walk_forward(
    trades: Sequence[Trade],
    *,
    n_folds: int = 3,
    min_train_frac: float = 0.4,
    initial_balance: float | None = None,
    timeframe: str | None = None,
    periods_per_year: float | None = None,
) -> dict[str, object]:
    """Rolling walk-forward (expanding window) out-of-sample evaluation.

    The first ``min_train_frac`` of the timeline trains fold 0; every fold
    then appends the next ``(1 - min_train_frac)/n_folds`` block as its test
    slice and carries the accumulated training window forward. Each fold's
    test is uncharted data when its fold is evaluated — the whole point of the
    walk — and the running starting balance carries the realized P&L forward.
    """
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    if not 0.0 < min_train_frac < 1.0:
        raise ValueError("min_train_frac must be in (0, 1)")
    ordered = [
        t
        for t in sorted(trades, key=lambda t: _naive(_ts(t.get("exit_ts")) or datetime.min))
        if _ts(t.get("exit_ts")) is not None
    ]
    if not ordered:
        return {"count": 0, "n_folds": n_folds, "note": "no trades to walk"}
    test_size = max(1, int((1.0 - min_train_frac) * len(ordered) / n_folds))
    train_end = max(1, int(min_train_frac * len(ordered)))
    init = _resolve_initial(trades, initial_balance)

    folds: list[dict[str, object]] = []
    running_initial = init
    prev_train_initial = init
    while train_end < len(ordered) and len(folds) < n_folds:
        end = min(len(ordered), train_end + test_size)
        train = ordered[:train_end]
        test = ordered[train_end:end]
        train_m = _period_metrics(train, prev_train_initial, timeframe, periods_per_year)
        test_m = _period_metrics(test, running_initial, timeframe, periods_per_year)
        folds.append(
            {
                "fold": len(folds) + 1,
                "train_count": len(train),
                "test_count": len(test),
                "test_start": test[0].get("exit_ts"),
                "test_end": test[-1].get("exit_ts"),
                "in_sample": train_m,
                "out_of_sample": test_m,
                "gap_cagr_pct": _gap(test_m.get("cagr_pct"), train_m.get("cagr_pct")),
            }
        )
        running_initial += sum(_float(t.get("pnl")) or 0.0 for t in test)
        prev_train_initial = running_initial
        train_end = end

    oos_cagrs: list[float] = []
    oos_exps: list[float] = []
    for fold in folds:
        oos = _foos(fold)
        c = _num(oos.get("cagr_pct"))
        e = _num(oos.get("expectancy_r"))
        if c is not None:
            oos_cagrs.append(c)
        if e is not None:
            oos_exps.append(e)
    aggregate: dict[str, float | None] = {
        "oos_cagr_median_pct": stats.median(oos_cagrs) if oos_cagrs else None,
        "oos_expectancy_median_r": stats.median(oos_exps) if oos_exps else None,
        "best_oos_cagr_pct": max(oos_cagrs) if oos_cagrs else None,
        "worst_oos_cagr_pct": min(oos_cagrs) if oos_cagrs else None,
    }
    return {
        "count": len(ordered),
        "n_folds": len(folds),
        "requested_folds": n_folds,
        "test_size": test_size,
        "min_train_frac": min_train_frac,
        "folds": folds,
        "aggregate": aggregate,
        "note": (
            "expanding-window walk: each fold's test slice is unseen at its "
            "evaluation time; running balance carries realized P&L forward"
        ),
    }


def risk_sensitivity(
    trades: Sequence[Trade],
    *,
    factors: Sequence[float] = (0.5, 1.0, 2.0),
    base_risk_fraction: float | None = None,
    n_sims: int = 500,
    seed: int = 42,
    initial_balance: float | None = None,
) -> dict[str, object]:
    """Parameter-sensitivity stub: nudge the risk fraction and watch CAGR/DD move.

    The backlog asks for a sensitivity run over nudged *strategy parameters*;
    those are driveable from strategy config later. Today the only knob the
    metrics layer owns is the MC compounding fraction, so that is what gets
    nudged (0.5x/1x/2x of the estimated base). Each row is a full resample MC.
    """
    base = _resolve_risk_fraction(
        trades, _resolve_initial(trades, initial_balance), base_risk_fraction
    )
    rows: list[dict[str, object]] = []
    for factor in factors:
        mc = monte_carlo(
            trades,
            n_sims=n_sims,
            seed=seed,
            mode="resample",
            initial_balance=initial_balance,
            risk_fraction=base * float(factor),
        )
        ci = mc["confidence_intervals"]
        neg = mc["negative_return_probability"]
        assert isinstance(ci, dict) and isinstance(neg, dict)
        dd = ci["max_drawdown_pct"]
        cagr = ci["cagr"]
        assert isinstance(dd, dict) and isinstance(cagr, dict)
        rows.append(
            {
                "factor": float(factor),
                "risk_fraction": mc["risk_fraction"],
                "cagr_p50_pct": cagr.get("p50"),
                "cagr_p5_pct": cagr.get("p5"),
                "max_drawdown_p50_pct": dd.get("p50"),
                "max_drawdown_p95_pct": dd.get("p95"),
                "neg_return_1y_prob": neg.get("1y"),
            }
        )
    return {
        "base_risk_fraction": base,
        "n_sims": n_sims,
        "seed": seed,
        "rows": rows,
        "note": (
            "stub over the MC risk-fraction knob; strategy-config parameter "
            "sensitivity becomes driveable from the strategy file later"
        ),
    }
