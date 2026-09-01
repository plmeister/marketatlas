from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from marketatlas.backtesting.portfolio import PortfolioBacktestResult
from marketatlas.data.store import MarketStore
from marketatlas.frames.output import from_portfolio_instrument
from marketatlas.visualization.interactive import InteractiveRenderer


def render_per_instrument_charts(
    result: PortfolioBacktestResult,
    stores: Mapping[str, MarketStore],
    output_dir: Path,
    stem: str = "portfolio",
) -> tuple[Path, ...]:
    """Render one interactive chart per instrument (backlog 077).

    ``InteractiveRenderer`` is reused as-is; each chart gets a per-instrument
    ``AnalysisOutput`` (that instrument's candles, frames and filtered trades)
    so trade markers and the summary bar reflect only that instrument. The
    canonical name drives the chart title and the ``{stem}.{canonical}.html``
    filename.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for inst in result.instruments:
        chart_path = output_dir / f"{stem}.{inst.canonical}.html"
        out = from_portfolio_instrument(result, inst.canonical, stores[inst.canonical])
        InteractiveRenderer(out).render(chart_path)
        paths.append(chart_path)
    return tuple(paths)


def render_portfolio_index(
    result: PortfolioBacktestResult,
    output_dir: Path,
    stem: str = "portfolio",
) -> Path:
    """Render the lightweight portfolio index page (backlog 077).

    The summary bar and every per-instrument row come straight from the shared
    ``TradeBook.summary`` — no recompute. Each row links to its
    ``{stem}.{canonical}.html`` chart via a relative href, so the page works
    from disk without a server.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary: Any = result.tradebook.summary
    by_instrument = summary.get("by_instrument")
    by_instrument = by_instrument if isinstance(by_instrument, dict) else {}
    by_strategy = summary.get("by_strategy")
    by_strategy = by_strategy if isinstance(by_strategy, dict) else {}
    monthly = result.tradebook.monthly_summary()

    total_pnl = float(summary.get("total_pnl", 0.0))
    pnl_class = _sign_class(total_pnl)
    expectancy = float(summary.get("expectancy", 0.0))
    exp_class = _sign_class(expectancy)

    instrument_rows = "\n".join(
        _instrument_row(
            inst.canonical,
            by_instrument.get(inst.canonical, {}),
            href=f"{stem}.{inst.canonical}.html",
        )
        for inst in result.instruments
    )
    strategy_rows = _strategy_rows_html(by_strategy)

    title = f"Portfolio: {', '.join(i.canonical for i in result.instruments)}"
    meta = (
        f"{len(result.instruments)} instrument(s) | "
        f"{int(summary.get('total_trades', 0))} trades | "
        f"window {result.window_size} | hold {result.max_hold_days}d"
    )

    html = _INDEX_TEMPLATE.format(
        css=_INDEX_CSS,
        title=title,
        meta=meta,
        final_balance=_fmt_money(float(summary.get("final_balance", 0.0))),
        total_pnl=_fmt_pnl(total_pnl),
        pnl_class=pnl_class,
        total_return=_fmt_pct(float(summary.get("total_return_pct", 0.0))),
        max_drawdown=_fmt_pct(float(summary.get("max_drawdown", 0.0))),
        total_trades=int(summary.get("total_trades", 0)),
        wins=int(summary.get("wins", 0)),
        losses=int(summary.get("losses", 0)),
        win_rate=_fmt_rate(float(summary.get("win_rate", 0.0))),
        profit_factor=_fmt_pf(float(summary.get("profit_factor", 0.0))),
        expectancy=_fmt_pnl(expectancy),
        exp_class=exp_class,
        instrument_rows=instrument_rows,
        strategy_rows=strategy_rows,
        monthly_rows=_monthly_rows_html(monthly),
    )

    index_path = output_dir / f"{stem}.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path


def render_portfolio(
    result: PortfolioBacktestResult,
    stores: Mapping[str, MarketStore],
    output_dir: Path,
    stem: str = "portfolio",
) -> tuple[Path, tuple[Path, ...]]:
    """Render the full portfolio visualization suite (backlog 077).

    Writes one interactive chart per instrument plus the index page; returns
    the index path and the chart paths. ``stores`` maps each canonical name to
    its ``MarketStore``.
    """
    charts = render_per_instrument_charts(result, stores, output_dir, stem)
    index = render_portfolio_index(result, output_dir, stem)
    return index, charts


def render_ab_index(
    rows: Sequence[tuple[Mapping[str, object], PortfolioBacktestResult]],
    output_dir: Path,
    stem: str = "ab",
    *,
    chart_name: str = "portfolio.{canonical}.html",
    instruments: Sequence[str] | None = None,
) -> Path:
    """Render the A/B comparison index page (backlog 081).

    ``rows`` pairs each variant's choice identity (079) with its backtest
    result. The page shows a summary grid — one row per variant whose columns
    are the varying choice dimensions plus the shared-book metrics straight
    from ``TradeBook.summary`` — then per-variant by-instrument and
    by-strategy tables reusing the ``render_portfolio_index`` markup. Each
    instrument row links to its 080 per-variant chart via a relative href, so
    the page works from disk without a server.

    ``chart_name`` names the chart file inside each variant directory (a
    ``{canonical}`` format string; the single-symbol path passes a fixed
    filename). ``instruments`` gives the canonical instrument names when the
    results are not ``PortfolioBacktestResult``.

    Backlog 082: the page is progressively enhanced with a control bar — one
    ``<select>`` per choice dimension — driven by a single embedded JSON blob
    (``AB_VARIANTS``/``AB_DIMS``, built from the same summaries the tables use).
    The summary grid is re-rendered from that JSON by a small inline, dependency-
    free script (mirroring the ``InteractiveRenderer`` inline-script style);
    detail sections carry a ``data-slug`` the script shows/hides. With JS
    disabled the page degrades to the full static 081 view — tables stay
    server-rendered and the JSON is purely additive.
    """
    from marketatlas.analysis.ast.variant import variant_columns

    output_dir.mkdir(parents=True, exist_ok=True)
    identities = [ident for ident, _ in rows]
    varying, headers, slugs = variant_columns(identities)

    first = rows[0][1] if rows else None
    if instruments is None:
        instruments = [i.canonical for i in first.instruments] if first is not None else []

    grid_rows: list[str] = []
    sections: list[str] = []
    variants: list[dict[str, Any]] = []
    for (ident, result), slug in zip(rows, slugs):
        summary: Any = result.tradebook.summary
        by_instrument = summary.get("by_instrument")
        by_instrument = by_instrument if isinstance(by_instrument, dict) else {}
        by_strategy = summary.get("by_strategy")
        by_strategy = by_strategy if isinstance(by_strategy, dict) else {}
        grid_rows.append(_ab_grid_row(ident, varying, summary))
        sections.append(
            _ab_variant_section(
                ident,
                varying,
                headers,
                by_instrument,
                by_strategy,
                instruments,
                slug,
                chart_name,
            )
        )
        variants.append(_ab_variant_json(ident, varying, summary, slug))

    variants_json = json.dumps(variants, ensure_ascii=False).replace("</", "<\\/") + ";"
    js = _AB_INDEX_JS.replace("null; // @data:VARIANTS", variants_json)
    js = js.replace(
        "null; // @data:DIMS", json.dumps(_ab_dims_json(identities, varying, headers)) + ";"
    )

    title = f"A/B Comparison — {len(rows)} variant(s)"
    meta = f"{len(rows)} variant(s) | {len(instruments)} instrument(s)"
    html = _AB_INDEX_TEMPLATE.format(
        css=_AB_INDEX_CSS,
        title=title,
        meta=meta,
        count=f"{len(rows)} variant(s)",
        choice_headers="".join(f"<th>{h}</th>" for h in headers),
        metric_headers=_METRIC_HEADERS,
        grid_rows="\n".join(grid_rows),
        detail_sections="\n".join(sections),
        ab_js=js,
    )

    index_path = output_dir / f"{stem}.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path


def _ab_grid_row(
    ident: Mapping[str, object],
    varying: Sequence[str],
    summary: Mapping[str, Any],
) -> str:
    choice_cells = "".join(f"<td>{ident[k]}</td>" for k in varying)
    total_pnl = float(summary.get("total_pnl", 0.0))
    wins = int(summary.get("wins", 0))
    losses = int(summary.get("losses", 0))
    expectancy = float(summary.get("expectancy", 0.0))
    return (
        f"<tr>{choice_cells}"
        f"<td>{int(summary.get('total_trades', 0))}</td>"
        f"<td>{wins}-{losses}</td>"
        f"<td>{_fmt_rate(float(summary.get('win_rate', 0.0)))}</td>"
        f'<td class="{_sign_class(total_pnl)}">{_fmt_pnl(total_pnl)}</td>'
        f"<td>{_fmt_pct(float(summary.get('total_return_pct', 0.0)))}</td>"
        f"<td>{_fmt_pct(float(summary.get('max_drawdown', 0.0)))}</td>"
        f"<td>{_fmt_pf(float(summary.get('profit_factor', 0.0)))}</td>"
        f'<td class="{_sign_class(expectancy)}">{_fmt_pnl(expectancy)}</td></tr>'
    )


def _ab_variant_json(
    ident: Mapping[str, object],
    varying: Sequence[str],
    summary: Mapping[str, Any],
    slug: str,
) -> dict[str, Any]:
    """Variant data for the embedded JSON (backlog 082).

    Numbers come from the same ``summary`` the server-rendered grid cells are
    formatted from, so the JS-rendered grid matches the no-JS tables exactly;
    ``ident`` values are stored as strings because that is how the grid cells
    render them. The unit test asserts this JSON against the static markup.
    """
    return {
        "slug": slug,
        "ident": {k: str(ident[k]) for k in varying},
        "metrics": {
            "total_trades": int(summary.get("total_trades", 0)),
            "wins": int(summary.get("wins", 0)),
            "losses": int(summary.get("losses", 0)),
            "win_rate": float(summary.get("win_rate", 0.0)),
            "total_pnl": float(summary.get("total_pnl", 0.0)),
            "total_return_pct": float(summary.get("total_return_pct", 0.0)),
            "max_drawdown": float(summary.get("max_drawdown", 0.0)),
            "profit_factor": float(summary.get("profit_factor", 0.0)),
            "expectancy": float(summary.get("expectancy", 0.0)),
        },
    }


def _ab_dims_json(
    identities: Sequence[Mapping[str, object]],
    varying: Sequence[str],
    headers: Sequence[str],
) -> list[dict[str, Any]]:
    """Choice dimensions (key/header/distinct option values) for the controls."""
    dims: list[dict[str, Any]] = []
    for key, header in zip(varying, headers):
        raw_values = sorted({i.get(key) for i in identities}, key=_option_sort_key)
        dims.append({"key": key, "header": header, "values": [str(v) for v in raw_values]})
    return dims


def _option_sort_key(value: object) -> tuple[object, ...]:
    """Deterministic option ordering across bool/int/float/str choice values."""
    if isinstance(value, bool):
        return (2, str(value))
    if isinstance(value, int | float):
        return (0, float(value), str(value))
    return (1, str(value))


def _ab_variant_section(
    ident: Mapping[str, object],
    varying: Sequence[str],
    headers: Sequence[str],
    by_instrument: Mapping[str, Any],
    by_strategy: Mapping[str, Any],
    instruments: Sequence[str],
    slug: str,
    chart_name: str,
) -> str:
    label = ", ".join(f"{h}={ident[k]}" for k, h in zip(varying, headers)) or "default"
    instrument_rows = "\n".join(
        _instrument_row(
            canonical,
            by_instrument.get(canonical, {}),
            href=f"{slug}/{chart_name.format(canonical=canonical)}",
        )
        for canonical in instruments
    )
    strategy_rows = _strategy_rows_html(by_strategy)
    return (
        f'<section class="variant" data-slug="{slug}">\n'
        f"<h2>Variant: {label}</h2>\n"
        "<h2>By Instrument</h2>\n"
        "<table>\n<thead>\n"
        "<tr><th>Instrument</th><th>P&amp;L</th><th>Trades</th>"
        "<th>W-L</th><th>Win rate</th><th>Profit factor</th></tr>\n"
        "</thead>\n<tbody>\n"
        + instrument_rows
        + "\n</tbody>\n</table>\n"
        + strategy_rows
        + "\n</section>"
    )


def _instrument_row(canonical: str, entry: Mapping[str, Any], href: str) -> str:
    total_pnl = float(entry.get("total_pnl", 0.0))
    trades = int(entry.get("trades", 0))
    wins = int(entry.get("wins", 0))
    losses = int(entry.get("losses", 0))
    win_rate = float(entry.get("win_rate", 0.0))
    pf = float(entry.get("profit_factor", 0.0))
    return (
        f'<tr><td><a href="{href}">{canonical}</a></td>'
        f'<td class="{_sign_class(total_pnl)}">{_fmt_pnl(total_pnl)}</td>'
        f"<td>{trades}</td>"
        f"<td>{wins}-{losses}</td>"
        f"<td>{_fmt_rate(win_rate)}</td>"
        f"<td>{_fmt_pf(pf)}</td></tr>"
    )


def _strategy_rows_html(by_strategy: Mapping[str, Any]) -> str:
    rows: list[str] = []
    for name, entry in by_strategy.items():
        if not isinstance(entry, dict):
            continue
        total_pnl = float(entry.get("total_pnl", 0.0))
        trades = int(entry.get("trades", 0))
        wins = int(entry.get("wins", 0))
        losses = int(entry.get("losses", 0))
        win_rate = float(entry.get("win_rate", 0.0))
        pf = float(entry.get("profit_factor", 0.0))
        rows.append(
            f"<tr><td>{name}</td>"
            f'<td class="{_sign_class(total_pnl)}">{_fmt_pnl(total_pnl)}</td>'
            f"<td>{trades}</td>"
            f"<td>{wins}-{losses}</td>"
            f"<td>{_fmt_rate(win_rate)}</td>"
            f"<td>{_fmt_pf(pf)}</td></tr>"
        )
    if not rows:
        return ""
    return (
        "<h2>By Strategy</h2>\n"
        "<table>\n<thead>\n"
        "<tr><th>Strategy</th><th>P&amp;L</th><th>Trades</th>"
        "<th>W-L</th><th>Win rate</th><th>Profit factor</th></tr>\n"
        "</thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>"
    )


def _monthly_rows_html(monthly: Mapping[str, Any]) -> str:
    rows: list[str] = []
    for month, entry in monthly.items():
        if not isinstance(entry, dict):
            continue
        total_pnl = float(entry.get("total_pnl", 0.0))
        growth = float(entry.get("growth_pct", 0.0))
        trades = int(entry.get("trades", 0))
        wins = int(entry.get("wins", 0))
        losses = int(entry.get("losses", 0))
        rows.append(
            f"<tr><td>{month}</td>"
            f'<td class="{_sign_class(total_pnl)}">{_fmt_pnl(total_pnl)}</td>'
            f'<td class="{_sign_class(growth)}">{_fmt_pct(growth)}</td>'
            f"<td>{trades}</td>"
            f"<td>{wins}-{losses}</td></tr>"
        )
    if not rows:
        return ""
    return (
        "<h2>Monthly</h2>\n"
        "<table>\n<thead>\n"
        "<tr><th>Month</th><th>P&amp;L</th><th>Growth</th><th>Trades</th><th>W-L</th></tr>\n"
        "</thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>"
    )


def _fmt_pnl(value: float) -> str:
    return f"{value:+.2f}"


def _fmt_money(value: float) -> str:
    return f"${value:.2f}"


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def _fmt_rate(value: float) -> str:
    return f"{value * 100:.1f}%"


def _fmt_pf(value: float) -> str:
    if math.isinf(value):
        return "\u221e"
    return f"{value:.2f}"


def _sign_class(value: float) -> str:
    if value > 0:
        return "num-pos"
    if value < 0:
        return "num-neg"
    return "num-zero"


_INDEX_CSS = """\
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #1a1a2e; color: #e0e0e0; padding-bottom: 40px; }
  header { padding: 16px 24px; background: #16213e; border-bottom: 1px solid #0f3460; }
  header h1 { font-size: 18px; font-weight: 600; color: #e94560; }
  header .meta { font-size: 12px; color: #888; margin-top: 4px; }
  .summary-bar { display: flex; flex-wrap: wrap; gap: 24px; padding: 12px 24px;
                 background: #0f3460; border-bottom: 1px solid #16213e; font-size: 13px; }
  .summary-bar .stat { color: #94a3b8; }
  .summary-bar .stat b { color: #e0e0e0; font-weight: 600; }
  .num-pos { color: #22c55e; }
  .num-neg { color: #ef4444; }
  .num-zero { color: #94a3b8; }
  main { padding: 20px 24px; }
  h2 { font-size: 15px; color: #e94560; margin: 24px 0 10px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: right; padding: 8px 10px; border-bottom: 1px solid #16213e; }
  th { color: #64748b; font-weight: 500; font-size: 11px; text-transform: uppercase; }
  th:first-child, td:first-child { text-align: left; }
  td:first-child a { color: #e0e0e0; text-decoration: none; font-weight: 600; }
  td:first-child a:hover { color: #e94560; text-decoration: underline; }
"""

_AB_INDEX_CSS = (
    _INDEX_CSS
    + """\
  .variant { border: 1px solid #0f3460; border-radius: 6px;
             padding: 4px 16px 16px; margin-top: 24px; }
  .variant h2:first-child { margin-top: 14px; }
  #ab-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
                 padding: 10px 0; border-bottom: 1px solid #16213e; }
  #ab-controls label { font-size: 12px; color: #94a3b8;
                       display: flex; align-items: center; gap: 6px; }
  #ab-controls select { background: #0f3460; color: #e0e0e0;
                        border: 1px solid #1a3a5c; padding: 3px 6px;
                        border-radius: 4px; font-size: 12px; }
  #ab-count { font-size: 12px; color: #64748b; margin-left: auto; }
"""
)

_METRIC_HEADERS = (
    "<th>Trades</th><th>W-L</th><th>Win rate</th><th>P&amp;L</th>"
    "<th>Return</th><th>Max Drawdown</th><th>Profit factor</th><th>Expectancy</th>"
)

_INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">{meta}</div>
</header>
<div class="summary-bar">
  <span class="stat">Balance: <b>{final_balance}</b></span>
  <span class="stat">Total P&amp;L: <b class="{pnl_class}">{total_pnl}</b></span>
  <span class="stat">Return: <b>{total_return}</b></span>
  <span class="stat">Max Drawdown: <b>{max_drawdown}</b></span>
  <span class="stat">Trades: <b>{total_trades}</b></span>
  <span class="stat">W/L: <b>{wins}-{losses}</b></span>
  <span class="stat">Win rate: <b>{win_rate}</b></span>
  <span class="stat">Profit factor: <b>{profit_factor}</b></span>
  <span class="stat">Expectancy: <b class="{exp_class}">{expectancy}</b></span>
</div>
<main>
  <h2>By Instrument</h2>
  <table>
    <thead>
      <tr><th>Instrument</th><th>P&amp;L</th><th>Trades</th>
          <th>W-L</th><th>Win rate</th><th>Profit factor</th></tr>
    </thead>
    <tbody>
{instrument_rows}
    </tbody>
  </table>
{strategy_rows}
{monthly_rows}
</main>
</body>
</html>
"""

_AB_INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">{meta}</div>
</header>
<main>
  <div id="ab-controls"><span id="ab-count">{count}</span></div>
  <h2>Comparison</h2>
  <table>
    <thead>
      <tr>{choice_headers}{metric_headers}</tr>
    </thead>
    <tbody id="ab-grid-body">
{grid_rows}
    </tbody>
  </table>
{detail_sections}
</main>
<script>
{ab_js}
</script>
</body>
</html>
"""

_AB_INDEX_JS = """\
// Backlog 082: progressive control bar for the A/B index. With the script
// disabled the page keeps the full static 081 tables; this block only rebuilds
// the summary grid from the embedded JSON and shows/hides detail sections.
/* global document */
// @data declarations (replaced by Python generator)
const AB_VARIANTS = null; // @data:VARIANTS
const AB_DIMS = null; // @data:DIMS

(function () {
  const variants = AB_VARIANTS;
  const dims = AB_DIMS;
  if (!variants || !dims) return;
  const gridBody = document.getElementById("ab-grid-body");
  const controls = document.getElementById("ab-controls");
  const countEl = document.getElementById("ab-count");
  const selects = {};

  function signClass(v) {
    return v > 0 ? "num-pos" : v < 0 ? "num-neg" : "num-zero";
  }

  function fmtPnl(v) {
    return (v >= 0 ? "+" : "") + v.toFixed(2);
  }

  function fmtPct(v) {
    return v.toFixed(1) + "%";
  }

  function fmtRate(v) {
    return (v * 100).toFixed(1) + "%";
  }

  function fmtPf(v) {
    return isFinite(v) ? v.toFixed(2) : "\\u221e";
  }

  function matches(variant) {
    for (let i = 0; i < dims.length; i++) {
      const sel = selects[dims[i].key];
      if (sel && sel.value !== "" && String(variant.ident[dims[i].key]) !== sel.value) {
        return false;
      }
    }
    return true;
  }

  function render() {
    let html = "";
    const shown = {};
    for (let i = 0; i < variants.length; i++) {
      const v = variants[i];
      if (!matches(v)) continue;
      shown[v.slug] = true;
      const m = v.metrics;
      let cells = "";
      for (let j = 0; j < dims.length; j++) {
        cells += "<td>" + v.ident[dims[j].key] + "</td>";
      }
      html += "<tr>" + cells +
        "<td>" + m.total_trades + "</td>" +
        "<td>" + m.wins + "-" + m.losses + "</td>" +
        "<td>" + fmtRate(m.win_rate) + "</td>" +
        "<td class=\\"" + signClass(m.total_pnl) + "\\">" + fmtPnl(m.total_pnl) + "</td>" +
        "<td>" + fmtPct(m.total_return_pct) + "</td>" +
        "<td>" + fmtPct(m.max_drawdown) + "</td>" +
        "<td>" + fmtPf(m.profit_factor) + "</td>" +
        "<td class=\\"" + signClass(m.expectancy) + "\\">" + fmtPnl(m.expectancy) +
        "</td></tr>";
    }
    if (gridBody) gridBody.innerHTML = html;
    const sections = document.querySelectorAll("section.variant");
    for (let k = 0; k < sections.length; k++) {
      sections[k].style.display = shown[sections[k].getAttribute("data-slug")] ? "" : "none";
    }
    if (countEl) {
      let n = 0;
      for (const s in shown) {
        if (Object.prototype.hasOwnProperty.call(shown, s)) n++;
      }
      countEl.textContent = n + " variant(s)";
    }
  }

  if (controls) {
    for (let d = 0; d < dims.length; d++) {
      const dim = dims[d];
      const label = document.createElement("label");
      label.textContent = dim.header + ": ";
      const sel = document.createElement("select");
      const all = document.createElement("option");
      all.value = "";
      all.textContent = "All";
      sel.appendChild(all);
      for (let a = 0; a < dim.values.length; a++) {
        const opt = document.createElement("option");
        opt.value = dim.values[a];
        opt.textContent = dim.values[a];
        sel.appendChild(opt);
      }
      sel.addEventListener("change", render);
      selects[dim.key] = sel;
      label.appendChild(sel);
      controls.appendChild(label);
    }
  }
  render();
})();
"""
