"""Metrics report dashboard (backlog 102-B).

Assembles the whole 098-102 metrics stack — trade-level (099), portfolio /
equity (100), costs / net (101), robustness (102) — into one payload, plus the
human "does it double?" verdict the whole stack exists to answer.

``build_report`` is a pure function over plain dicts (trades + optional equity
curve + optional cost schedule): JSON-serializable, no I/O, callable from the
CLI or a notebook. ``format_report_text`` renders the payload as a CLI table;
``payload_to_json`` is the machine shape.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from marketatlas.metrics.costs import CostSchedule, net_metrics
from marketatlas.metrics.portfolio import portfolio_metrics
from marketatlas.metrics.robustness import (
    monte_carlo,
    out_of_sample_split,
    risk_sensitivity,
    walk_forward,
)
from marketatlas.metrics.trades import trade_metrics

Trade = Mapping[str, Any]

_DOUBLE_TARGET_PCT = 100.0

_MC_KEY = (5, 25, 50, 75, 95)


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(float(value)) else None
    return None


def _pct(value: float) -> str:
    """Percent rendering that keeps small values readable (0.36%, not 0%)."""
    v = abs(value)
    if v >= 10.0:
        return f"{value:.0f}%"
    if v >= 1.0:
        return f"{value:.1f}%"
    return f"{value:.2f}%"


def _cagr_mc_band(mc: Mapping[str, object]) -> tuple[float | None, float | None, float | None]:
    ci = mc.get("confidence_intervals")
    if not isinstance(ci, Mapping):
        return None, None, None
    cagr = ci.get("cagr")
    if not isinstance(cagr, Mapping):
        return None, None, None
    return (
        _num(cagr.get("p5")),
        _num(cagr.get("p50")),
        _num(cagr.get("p95")),
    )


def _verdict(
    cagr_pct: float | None,
    mc: Mapping[str, object] | None,
    target_pct: float,
) -> dict[str, object]:
    """The "does it double?" line: CAGR vs target with its MC confidence band.

    ``reliable`` = the MC 5th percentile of CAGR is positive (the edge
    survives the resampled worst cases); ``doubles`` = median (or observed)
    CAGR clears the target. The line carries both.
    """
    p5, p50, p95 = (None, None, None)
    if mc is not None:
        p5, p50, p95 = _cagr_mc_band(mc)
    observed = cagr_pct
    doubles = observed is not None and observed >= target_pct
    reliable = p5 is not None and p5 > 0.0
    point = observed if observed is not None else p50
    if point is None:
        line = f"no CAGR data — cannot judge against the {target_pct:g}%/yr target"
    else:
        band = _pct(point)
        if p5 is not None and p95 is not None:
            band += f" [P5-P95: {_pct(p5)}-{_pct(p95)}]"
        else:
            band += " [no MC band]"
        if doubles and reliable:
            conclusion = "doubles target and survives resampling"
        elif doubles:
            conclusion = "clears target but the MC band includes failure — not yet reliable"
        elif reliable:
            conclusion = f"below the {target_pct:g}%/yr target, but the edge is positive"
        else:
            conclusion = f"not at the {target_pct:g}%/yr doubling target and not reliable"
        line = f"CAGR {band} vs {target_pct:g}%/yr target: {conclusion}"
    return {
        "target_cagr_pct": target_pct,
        "observed_cagr_pct": observed,
        "mc_cagr_p5_pct": p5,
        "mc_cagr_p50_pct": p50,
        "mc_cagr_p95_pct": p95,
        "doubles": doubles,
        "reliable": reliable,
        "line": line,
    }


def _per_year(portfolio: Mapping[str, object]) -> dict[str, object]:
    returns = portfolio.get("returns")
    if not isinstance(returns, Mapping):
        return {"annual": [], "std_pct": None, "count": 0}
    annual = returns.get("annual")
    if not isinstance(annual, list):
        return {"annual": [], "std_pct": None, "count": 0}
    rows: dict[str, float | None] = {}
    pcts: list[float] = []
    for item in annual:
        if not isinstance(item, Mapping):
            continue
        period = item.get("period")
        ret = _num(item.get("return_pct"))
        if isinstance(period, str):
            rows[period] = ret
            if ret is not None:
                pcts.append(ret)
    return {
        "annual": rows,
        "std_pct": float(stats_std(pcts)) if len(pcts) > 0 else None,
        "best_pct": max(pcts) if pcts else None,
        "worst_pct": min(pcts) if pcts else None,
        "count": len(pcts),
    }


def stats_std(values: Sequence[float]) -> float:
    import statistics

    return (
        float(statistics.stdev(values)) if len(values) > 1 else float(values[0]) if values else 0.0
    )


def _per_instrument(
    trades_by_instrument: Mapping[str, Sequence[Trade]],
) -> dict[str, object]:
    rows: dict[str, dict[str, object]] = {}
    exps: list[float] = []
    for name, group in sorted(trades_by_instrument.items()):
        tm = trade_metrics(group)
        expectancy = tm.get("expectancy")
        counts = tm.get("counts")
        wr = tm.get("win_rate")
        pf = tm.get("profit_factor")
        exp = _num(expectancy.get("expectancy_r")) if isinstance(expectancy, Mapping) else None
        if exp is not None:
            exps.append(exp)
        rows[name] = {
            "count": counts.get("total") if isinstance(counts, Mapping) else len(group),
            "win_rate": wr.get("decided") if isinstance(wr, Mapping) else None,
            "expectancy_r": exp,
            "profit_factor_r": pf.get("profit_factor_r") if isinstance(pf, Mapping) else None,
        }
    return {
        "by_instrument": rows,
        "expectancy_variance_r_std": stats_std(exps),
        "count": len(rows),
    }


def build_report(
    trades: Sequence[Trade],
    *,
    equity_curve: Sequence[Mapping[str, Any]] | None = None,
    initial_balance: float | None = None,
    timeframe: str | None = None,
    periods_per_year: float | None = None,
    cost_schedule: CostSchedule | None = None,
    seed: int = 42,
    n_sims: int = 1000,
    risk_fraction: float | None = None,
    target_cagr_pct: float = _DOUBLE_TARGET_PCT,
    trades_by_instrument: Mapping[str, Sequence[Trade]] | None = None,
) -> dict[str, object]:
    """Assemble the full metrics dashboard (098-102) into one payload.

    Every section is the output of the matching layer: 099 ``trade_metrics``
    (R-canonical trade stats), 100 ``portfolio_metrics`` (equity/risk
    ratios), 101 ``net_metrics`` (costs — present only when a schedule is
    given), 102 ``robustness`` (MC band + walk-forward + variance across
    periods/instruments + sensitivity stub). ``verdict`` is the headline
    answer, computed from the observed CAGR against its MC confidence band.
    Pure and JSON-serializable.
    """
    tm = trade_metrics(trades)
    pm = portfolio_metrics(trades, equity_curve, initial_balance, timeframe, periods_per_year)

    mc = monte_carlo(
        trades,
        n_sims=n_sims,
        seed=seed,
        mode="resample",
        initial_balance=initial_balance,
        risk_fraction=risk_fraction,
    )
    shuffle = monte_carlo(
        trades,
        n_sims=n_sims,
        seed=seed,
        mode="shuffle",
        initial_balance=initial_balance,
        risk_fraction=risk_fraction,
    )

    pm_ret = pm.get("returns")
    assert isinstance(pm_ret, Mapping)
    cagr = _num(pm_ret.get("cagr_pct"))
    observed = mc.get("observed")
    assert isinstance(observed, Mapping)
    cagr = cagr if cagr is not None else _num(observed.get("cagr_pct"))

    risk_report = {
        "monte_carlo": mc,
        "shuffle_order": shuffle,
        "out_of_sample": out_of_sample_split(
            trades,
            initial_balance=initial_balance,
            timeframe=timeframe,
            periods_per_year=periods_per_year,
        ),
        "walk_forward": walk_forward(
            trades,
            initial_balance=initial_balance,
            timeframe=timeframe,
            periods_per_year=periods_per_year,
        ),
        "parameter_sensitivity": risk_sensitivity(
            trades,
            base_risk_fraction=risk_fraction,
            n_sims=min(n_sims, 500),
            seed=seed,
            initial_balance=initial_balance,
        ),
        "per_period": _per_year(pm),
        "per_instrument": _per_instrument(trades_by_instrument or {}),
    }

    tm_counts = tm.get("counts")
    assert isinstance(tm_counts, Mapping)
    report: dict[str, object] = {
        "source": {
            "trades": len(trades),
            "decided": tm_counts.get("decided"),
            "timeframe": timeframe,
            "instruments": list((trades_by_instrument or {}).keys()) or ["-"],
        },
        "verdict": _verdict(cagr, mc, float(target_cagr_pct)),
        "trades": tm,
        "portfolio": pm,
        "robustness": risk_report,
        "note": (
            "R-canonical framing: expectancy/win rate/profit factor /reach are "
            "reported in R units; the 'does it double?' verdict compares CAGR "
            "against its Monte-Carlo confidence band, not the single number."
        ),
    }
    if cost_schedule is not None:
        report["net"] = net_metrics(
            trades,
            cost_schedule,
            initial_balance=initial_balance,
            timeframe=timeframe,
            periods_per_year=periods_per_year,
        )
    return report


def format_report_text(report: Mapping[str, object]) -> str:
    """Render the report payload as a CLI-readable text dashboard."""
    lines: list[str] = []
    verdict = report.get("verdict")
    if isinstance(verdict, Mapping):
        lines.append("=" * 62)
        lines.append("METRICS REPORT — shows whether the combination doubles")
        lines.append("=" * 62)
        line = verdict.get("line")
        if isinstance(line, str):
            lines.append(f"  {line}")
        lines.append("")

    src = report.get("source")
    if isinstance(src, Mapping):
        instruments = src.get("instruments")
        if isinstance(instruments, list):
            lines.append(
                f"  {src.get('trades')} trades across "
                f"{len(instruments)} instrument(s): "
                f"{', '.join(str(i) for i in instruments)}"
            )
        lines.append("")

    tm = report.get("trades")
    if isinstance(tm, Mapping):
        exp = tm.get("expectancy")
        pf = tm.get("profit_factor")
        wr = tm.get("win_rate")
        counts = tm.get("counts")
        if (
            isinstance(exp, Mapping)
            and isinstance(pf, Mapping)
            and isinstance(wr, Mapping)
            and isinstance(counts, Mapping)
        ):
            lines.append("Trade-level (099, R units):")
            _text_value(lines, "  Expectancy", exp.get("expectancy_r"), "R")
            _text_value(lines, "  Profit factor", pf.get("profit_factor_r"), "")
            _text_value(lines, "  Win rate (decided)", wr.get("decided"), "")
            lines.append(
                f"  Trades: {counts.get('total')} "
                f"({counts.get('wins')}W/{counts.get('losses')}L/"
                f"{counts.get('breakevens')}BE/{counts.get('cancelled')}C)"
            )
            lines.append("")

    pm = report.get("portfolio")
    if isinstance(pm, Mapping):
        lines.append("Portfolio / equity (100):")
        summary = pm.get("summary")
        returns = pm.get("returns")
        risk = pm.get("risk")
        dd = pm.get("drawdown")
        if (
            isinstance(summary, Mapping)
            and isinstance(returns, Mapping)
            and isinstance(risk, Mapping)
            and isinstance(dd, Mapping)
        ):
            _text_value(lines, "  CAGR", returns.get("cagr_pct"), "%")
            _text_value(lines, "  Total return", summary.get("total_return_pct"), "%")
            _text_value(lines, "  Final balance", summary.get("final_balance"), "")
            _text_value(lines, "  Max drawdown", dd.get("max_drawdown_pct"), "%")
            _text_value(lines, "  Sharpe", risk.get("sharpe"), "")
            _text_value(lines, "  Sortino", risk.get("sortino"), "")
            _text_value(lines, "  Calmar", risk.get("calmar"), "")
            _text_value(lines, "  Monthly vol (annual)", risk.get("volatility_pct_annual"), "%")
            _text_value(lines, "  Periods/yr basis", risk.get("annualization_basis"), "")
            lines.append("")

    net = report.get("net")
    if isinstance(net, Mapping):
        lines.append("Net after costs (101):")
        costs = net.get("costs")
        drags = net.get("drags")
        flips = net.get("sign_flips")
        if isinstance(costs, Mapping) and isinstance(drags, Mapping) and isinstance(flips, list):
            lines.append(
                f"  Costs paid: {costs.get('total_cost')} "
                f"({costs.get('costed_count')}/{costs.get('filled_count')} filled)"
            )
            _text_value(lines, "  Net CAGR", drags.get("cagr_drag_pct"), "%")
            _text_value(lines, "  Expectancy drag", drags.get("expectancy_drag_r"), "R")
            net_summary = (
                net.get("net", {}).get("portfolio", {}).get("summary")
                if isinstance(net.get("net"), Mapping)
                else None
            )
            _text_value(
                lines,
                "  Net total return",
                net_summary.get("total_return_pct") if isinstance(net_summary, Mapping) else None,
                "%",
            )
            if flips:
                lines.append("  Sign flips:")
                for flip in flips:
                    if isinstance(flip, Mapping):
                        lines.append(f"    {flip.get('signal')}")
            lines.append("")

    rob = report.get("robustness")
    if isinstance(rob, Mapping):
        mc = rob.get("monte_carlo")
        oos = rob.get("out_of_sample")
        wf = rob.get("walk_forward")
        sens = rob.get("parameter_sensitivity")
        if (
            isinstance(mc, Mapping)
            and isinstance(oos, Mapping)
            and isinstance(wf, Mapping)
            and isinstance(sens, Mapping)
        ):
            lines.append("Robustness (102):")
            obs = mc.get("observed")
            ciband = mc.get("confidence_intervals")
            if isinstance(obs, Mapping) and isinstance(ciband, Mapping):
                cagr = ciband.get("cagr")
                dd = mc.get("worst_case_drawdown")
                if isinstance(cagr, Mapping) and isinstance(dd, Mapping):
                    _mc_band(lines, cagr, "  MC CAGR")
                    _text_value(lines, "  MC worst-case DD (P95)", dd.get("p95_pct"), "%")
                _text_value(lines, "  Observed expectancy", obs.get("expectancy_r"), "R")
                _text_value(
                    lines, "  MC expectancy band", _mc_band_text(ciband.get("expectancy")), "R"
                )
            neg = mc.get("negative_return_probability")
            if isinstance(neg, Mapping):
                subs = {str(k): v for k, v in neg.items() if isinstance(k, str) and k.endswith("y")}
                if subs:
                    lines.append(
                        "  P(negative return): "
                        + ", ".join(
                            f"{k}->{v:.1%}" if isinstance(v, int | float) else f"{k}->{v}"
                            for k, v in sorted(subs.items())
                        )
                    )
            _text_value(
                lines,
                "  Walk-forward OOS CAGR (median)",
                _num(
                    wf.get("aggregate", {}).get("oos_cagr_median_pct")
                    if isinstance(wf.get("aggregate"), Mapping)
                    else None
                ),
                "%",
            )
            lines.append("")

    lines.append("=" * 62)
    lines.append("END REPORT")
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "n/a"
        return f"{value:.4g}".rstrip(".") if not value.is_integer() else f"{int(value)}"
    return str(value) if value is not None else "n/a"


def _mc_band_text(dist: Any) -> str | None:
    if not isinstance(dist, Mapping):
        return None
    p5, p50, p95 = dist.get("p5"), dist.get("p50"), dist.get("p95")
    if p5 is None or p50 is None or p95 is None:
        return "n/a"
    return f"{p5:g} / {p50:g} / {p95:g}"


def _mc_band(lines: list[str], dist: Mapping[str, Any], label: str) -> None:
    band = _mc_band_text(dist)
    lines.append(f"{label}: {band}  (P5 / P50 / P95)" if band else f"{label}: n/a")


def _text_value(lines: list[str], label: str, value: Any, unit: str = "") -> None:
    text = _fmt(value)
    if unit and text != "n/a":
        text += f" {unit}"
    lines.append(f"{label}: {text}")


def report_source_from_json(
    doc: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], str | None]:
    """Pull (trades, equity_curve, instruments, timeframe) out of a run JSON.

    Accepts either the single-instrument shape (``encode_analysis_output``:
    top-level ``trades``/``equity_curve``/``timeframe``) or the portfolio shape
    (``encode_portfolio``: ``per_instrument`` dict of those, plus a top-level
    ``equity_curve``). Trades are flattened in instrument order.
    """
    trades: list[dict[str, Any]] = []
    instruments: list[str] = []
    timeframe: str | None = None
    per_instrument = doc.get("per_instrument")
    if isinstance(per_instrument, Mapping):
        for canonical, out in per_instrument.items():
            if not isinstance(out, Mapping):
                continue
            instruments.append(str(canonical))
            if timeframe is None and isinstance(out.get("timeframe"), str):
                timeframe = out.get("timeframe")
            ts = out.get("trades")
            if isinstance(ts, list):
                trades.extend(dict(t) for t in ts if isinstance(t, dict))
        curve = doc.get("equity_curve")
        if isinstance(curve, list):
            curve_list = [dict(c) for c in curve if isinstance(c, dict)]
        else:
            curve_list = []
    else:
        instruments = [str(doc.get("symbol") or "-")]
        if isinstance(doc.get("timeframe"), str):
            timeframe = doc.get("timeframe")
        ts = doc.get("trades")
        if isinstance(ts, list):
            trades.extend(dict(t) for t in ts if isinstance(t, dict))
        raw_curve = doc.get("equity_curve")
        if isinstance(raw_curve, list):
            curve_list = [dict(c) for c in raw_curve if isinstance(c, dict)]
        else:
            curve_list = []
    return trades, curve_list, instruments, timeframe
