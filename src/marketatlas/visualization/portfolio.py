from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from marketatlas.backtesting.portfolio import PortfolioBacktestResult
from marketatlas.data.store import MarketStore
from marketatlas.visualization.context import RenderContext
from marketatlas.visualization.interactive import InteractiveRenderer


def render_per_instrument_charts(
    result: PortfolioBacktestResult,
    stores: Mapping[str, MarketStore],
    output_dir: Path,
    stem: str = "portfolio",
) -> tuple[Path, ...]:
    """Render one interactive chart per instrument (backlog 077).

    ``InteractiveRenderer`` is reused as-is; each chart gets the shared book
    filtered to that instrument's trades (``TradeBook.filtered_by_instrument``)
    so trade markers and the summary bar reflect only that instrument. The
    canonical name drives the chart title and the ``{stem}.{canonical}.html``
    filename.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for inst in result.instruments:
        chart_path = output_dir / f"{stem}.{inst.canonical}.html"
        ctx = RenderContext(
            frames=result.frames[inst.canonical],
            store=stores[inst.canonical],
            tradebook=result.tradebook.filtered_by_instrument(inst.canonical),
            title=inst.canonical,
            window_size=result.window_size,
            max_hold_days=result.max_hold_days,
        )
        InteractiveRenderer(ctx).render(chart_path)
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


_INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #1a1a2e; color: #e0e0e0; padding-bottom: 40px; }}
  header {{ padding: 16px 24px; background: #16213e; border-bottom: 1px solid #0f3460; }}
  header h1 {{ font-size: 18px; font-weight: 600; color: #e94560; }}
  header .meta {{ font-size: 12px; color: #888; margin-top: 4px; }}
  .summary-bar {{ display: flex; flex-wrap: wrap; gap: 24px; padding: 12px 24px;
                 background: #0f3460; border-bottom: 1px solid #16213e; font-size: 13px; }}
  .summary-bar .stat {{ color: #94a3b8; }}
  .summary-bar .stat b {{ color: #e0e0e0; font-weight: 600; }}
  .num-pos {{ color: #22c55e; }}
  .num-neg {{ color: #ef4444; }}
  .num-zero {{ color: #94a3b8; }}
  main {{ padding: 20px 24px; }}
  h2 {{ font-size: 15px; color: #e94560; margin: 24px 0 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: right; padding: 8px 10px; border-bottom: 1px solid #16213e; }}
  th {{ color: #64748b; font-weight: 500; font-size: 11px; text-transform: uppercase; }}
  th:first-child, td:first-child {{ text-align: left; }}
  td:first-child a {{ color: #e0e0e0; text-decoration: none; font-weight: 600; }}
  td:first-child a:hover {{ color: #e94560; text-decoration: underline; }}
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
</main>
</body>
</html>
"""
