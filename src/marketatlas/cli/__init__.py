from __future__ import annotations

import argparse

from marketatlas.cli.commands import (  # noqa: F401 — re-export for test patches
    _run_ab_test,
    _run_portfolio_ab_test,
    fetch_command,
    instruments_add_command,
    instruments_list_command,
    run_command,
    run_portfolio_command,
    snapshot_command,
)
from marketatlas.data.providers.dukascopy import DukascopyProvider  # noqa: F401 — re-export
from marketatlas.data.providers.yahoo import YahooProvider  # noqa: F401 — re-export

__all__ = [
    "DukascopyProvider",
    "YahooProvider",
    "_run_ab_test",
    "_run_portfolio_ab_test",
    "fetch_command",
    "instruments_add_command",
    "instruments_list_command",
    "main",
    "run_command",
    "run_portfolio_command",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="MarketAtlas CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch market data")
    fetch_parser.add_argument("--symbol", required=True, help="Symbol to fetch (e.g., BTCUSDT)")
    fetch_parser.add_argument("--timeframe", required=True, help="Timeframe (e.g., 1h, 1d)")
    fetch_parser.add_argument("--start", required=True, help="Start date (ISO format)")
    fetch_parser.add_argument("--end", required=True, help="End date (ISO format)")
    fetch_parser.add_argument("--output", default="data/", help="Output directory (default: data/)")
    fetch_parser.add_argument(
        "--registry",
        default="",
        help="Path to instruments registry YAML (default: data/instruments.yaml)",
    )

    run_parser = subparsers.add_parser("run", help="Run a strategy backtest")
    run_parser.add_argument("--strategy", "-s", required=True, help="Strategy file (DSL or YAML)")
    run_parser.add_argument(
        "--ab",
        action="store_true",
        help="A/B test: expand DSL template choices (<a | b | c>) into one backtest per variant",
    )
    run_parser.add_argument("--symbol", default="BTC-USD", help="Market symbol (default: BTC-USD)")
    run_parser.add_argument(
        "--instruments",
        default="",
        help="Portfolio YAML file listing canonical instrument names; "
        "loads data for all over the same range (ignores --symbol)",
    )
    run_parser.add_argument("--start", default="", help="Start date ISO (default: 2 years ago)")
    run_parser.add_argument("--end", default="", help="End date ISO (default: today)")
    run_parser.add_argument("--interval", default="1d", help="Candle interval (default: 1d)")
    run_parser.add_argument(
        "--output",
        "-o",
        default="/tmp/backtest_result.html",
        help="HTML output path",
    )
    run_parser.add_argument(
        "--pickle",
        default="",
        help="Also dump full backtest result (store, frames, tradebook) to this .pkl path",
    )
    run_parser.add_argument(
        "--output-json",
        default="",
        help="Also dump typed structured output (facts + trades) to this .json path",
    )
    run_parser.add_argument(
        "--snapshots",
        default="",
        help="Render annotated trade-snapshot PNGs into this directory; "
        "requires the 'snapshots' extra (matplotlib)",
    )
    run_parser.add_argument(
        "--kinds",
        default="",
        help="Comma-separated POI kinds to snapshot (trade,rejection,pattern,sr,"
        "swing); prefix with ! to exclude (e.g. !pattern). Default: all",
    )
    run_parser.add_argument(
        "--balance",
        type=float,
        default=1000.0,
        help="Starting balance (default: 1000)",
    )
    run_parser.add_argument(
        "--max-hold-days",
        type=int,
        default=10,
        help="Max hold days (default: 10)",
    )
    run_parser.add_argument(
        "--data-dir",
        default="",
        help="Persistent data store directory "
        "(default: $MARKETATLAS_DATA_DIR or ~/.cache/marketatlas/data)",
    )
    run_parser.add_argument(
        "--registry",
        default="",
        help="Path to instruments registry YAML (default: data/instruments.yaml)",
    )

    snap_parser = subparsers.add_parser(
        "snapshot",
        help="Render annotated trade-snapshot PNGs from a structured JSON output "
        "(requires the 'snapshots' extra: matplotlib)",
    )
    snap_parser.add_argument(
        "output_json",
        help="Path to structured JSON produced by `run --output-json`",
    )
    snap_parser.add_argument(
        "--outdir",
        "-o",
        default=".",
        help="Directory to write PNGs into (default: current dir)",
    )
    snap_parser.add_argument(
        "--timeframe",
        default=None,
        help="Force candle timeframe for rendering (default: each output's own)",
    )
    snap_parser.add_argument(
        "--overlays",
        default="",
        help="Comma-separated fact-series to plot on the price axis "
        "(e.g. ema,sma,atr; default: none)",
    )
    snap_parser.add_argument(
        "--no-volume",
        action="store_true",
        help="Skip the volume subplot",
    )
    snap_parser.add_argument(
        "--kinds",
        default="",
        help="Comma-separated POI kinds to snapshot (trade,rejection,pattern,sr,"
        "swing); prefix with ! to exclude (e.g. !pattern). Default: all",
    )

    instr_parser = subparsers.add_parser("instruments", help="Manage instrument registry")
    instr_sub = instr_parser.add_subparsers(dest="instr_command", help="Instrument command")

    list_parser = instr_sub.add_parser("list", help="List registered instruments")
    list_parser.add_argument("--registry", default="", help="Path to instruments YAML file")

    add_parser = instr_sub.add_parser("add", help="Add an instrument")
    add_parser.add_argument("canonical", help="Canonical name (e.g. EURUSD)")
    add_parser.add_argument(
        "--class",
        dest="asset_class",
        required=True,
        help="Asset class (forex, crypto, equity, commodity)",
    )
    add_parser.add_argument("--description", required=True, help="Human-readable description")
    add_parser.add_argument("--yahoo-symbol", help="Yahoo Finance symbol")
    add_parser.add_argument("--dukascopy-symbol", help="Dukascopy symbol")
    add_parser.add_argument("--oanda-symbol", help="OANDA symbol")
    add_parser.add_argument(
        "--provider-priority",
        default="",
        help="Comma-separated provider priority order (e.g. dukascopy,yahoo)",
    )
    add_parser.add_argument("--registry", default="", help="Path to instruments YAML file")

    args = parser.parse_args()

    if args.command == "fetch":
        fetch_command(args)
    elif args.command == "run":
        run_command(args)
    elif args.command == "instruments":
        if args.instr_command == "list":
            instruments_list_command(args)
        elif args.instr_command == "add":
            instruments_add_command(args)
        else:
            instr_parser.print_help()
    elif args.command == "snapshot":
        snapshot_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
