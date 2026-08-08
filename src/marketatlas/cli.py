from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from marketatlas.data.datastore import DataStore
from marketatlas.data.instrument import Instrument, InstrumentRegistry
from marketatlas.data.providers.yahoo import YahooProvider
from marketatlas.data.types import MarketData, Symbol, Timeframe


def _find_resample_source(
    target: Timeframe,
    fetched: dict[Timeframe, MarketData],
) -> Timeframe | None:
    from marketatlas.data.resample import tf_minutes

    target_mins = tf_minutes(target)
    candidates = [
        (tf, tf_minutes(tf))
        for tf in fetched
        if tf_minutes(tf) < target_mins
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda x: x[1])[0]


def fetch_command(args: argparse.Namespace) -> None:
    provider = YahooProvider()
    symbol = Symbol(args.symbol)
    timeframe = Timeframe(args.timeframe)
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    output_dir = Path(args.output)

    if not output_dir.exists():
        output_dir.mkdir(parents=True)

    try:
        market_data = provider.fetch(symbol, timeframe, start, end)
    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)

    import pyarrow as pa  # type: ignore[import-untyped]
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    table = pa.table(
        {
            "timestamp": [c.timestamp for c in market_data.candles],
            "open": [c.open for c in market_data.candles],
            "high": [c.high for c in market_data.candles],
            "low": [c.low for c in market_data.candles],
            "close": [c.close for c in market_data.candles],
            "volume": [c.volume for c in market_data.candles],
        }
    )

    output_path = output_dir / f"{symbol.name}.{timeframe.value}.parquet"
    pq.write_table(table, output_path)
    print(f"Saved {len(market_data.candles)} candles to {output_path}")


def run_command(args: argparse.Namespace) -> None:
    from marketatlas.backtesting.backtester import Backtester
    from marketatlas.data.resample import CannotResampleError, resample, tf_minutes
    from marketatlas.data.store import MarketStore
    from marketatlas.strategy.bundle import StrategyBundle
    from marketatlas.strategy.loader import load_strategy
    from marketatlas.strategy.strategy import Strategy
    from marketatlas.visualization.context import RenderContext
    from marketatlas.visualization.interactive import InteractiveRenderer

    strategy_path = Path(args.strategy)
    if not strategy_path.exists():
        print(f"Error: strategy file not found: {strategy_path}", file=sys.stderr)
        sys.exit(1)

    try:
        config = load_strategy(strategy_path)
    except Exception as e:
        print(f"Error loading strategy: {e}", file=sys.stderr)
        sys.exit(1)

    strategy = Strategy(config.name, config)
    bundle = StrategyBundle([strategy], initial_balance=args.balance)

    print(f"Strategy: {config.name} v{config.version}")
    print(f"Analyzers: {len(config.analyzers)}")
    print(f"Signals: {len(config.signals)}")

    symbol = Symbol(args.symbol)
    base_tf = Timeframe(args.interval)
    default_start = datetime.now() - timedelta(days=730)
    start = datetime.fromisoformat(args.start) if args.start else default_start
    end = datetime.fromisoformat(args.end) if args.end else datetime.now()

    config_tfs = [Timeframe(tf) for tf in config.timeframes]
    all_tfs = sorted(
        set([base_tf] + config_tfs), key=lambda tf: tf_minutes(tf)
    )
    print(f"\nFetching {len(all_tfs)} timeframe(s): {', '.join(tf.value for tf in all_tfs)}")
    print(f"Range: {start.date()} to {end.date()}")
    provider = YahooProvider()
    datastore = DataStore(Path(args.data_dir) if args.data_dir else None)
    print(f"Data store: {datastore.base_path}")

    fetched: dict[Timeframe, MarketData] = {}
    resampled: list[tuple[Timeframe, Timeframe]] = []

    for tf in all_tfs:
        # Serve from the persistent store when the range is already covered.
        if datastore.has(symbol, tf, start, end):
            md = datastore.get(symbol, tf, start, end)
            if md is not None and md.candles:
                fetched[tf] = md
                print(f"  {tf.value}: served from store ({len(md.candles)} candles)")
                continue

        # Try native fetch first
        try:
            md = provider.fetch(symbol, tf, start, end)
            datastore.put(md)
            fetched[tf] = md
            print(f"  {tf.value}: fetched natively ({len(md.candles)} candles)")
            continue
        except ValueError:
            pass
        except Exception as e:
            print(f"  {tf.value}: fetch error — {e}", file=sys.stderr)
            continue

        # Native not supported — try resample from nearest higher-res
        source_tf = _find_resample_source(tf, fetched)
        if source_tf is None:
            print(f"  {tf.value}: cannot fetch or resample (no source data)")
            continue

        try:
            candles = resample(fetched[source_tf].candles, source_tf, tf)
            md = MarketData(symbol=symbol, timeframe=tf, candles=candles)
            datastore.put(md)
            fetched[tf] = md
            resampled.append((tf, source_tf))
            print(f"  {tf.value}: resampled from {source_tf.value} ({len(candles)} candles)")
        except CannotResampleError as e:
            print(f"  {tf.value}: cannot resample — {e}")

    if base_tf not in fetched:
        print(f"Error: primary timeframe {base_tf.value} not available", file=sys.stderr)
        sys.exit(1)

    store = MarketStore(fetched)
    print(f"Data: {len(store)} candles ({store.timeframe.value})")
    print(f"Timeframes: {', '.join(tf.value for tf in store.available_timeframes)}")
    print(f"Resampled: {', '.join(f'{tf.value}←{src.value}' for tf, src in resampled) or 'none'}")
    print(f"Range: {store[0].timestamp.date()} to {store[-1].timestamp.date()}")
    print(f"Price: ${store[0].close:.2f} -> ${store[-1].close:.2f}")

    bt = Backtester(store, bundle, window_size=100, max_hold_days=args.max_hold_days)
    print(f"\nRunning backtest ({bt.frame_count} frames)...")

    def progress(cur: int, total: int) -> None:
        print(f"\r  Frame {cur}/{total}", end="", flush=True)

    result = bt.run_with_progress(progress)
    frame_store, tradebook = result.frames, result.tradebook
    print("\n")

    summary = tradebook.summary
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Initial balance: ${summary['initial_balance']:.2f}")
    print(f"  Final balance:   ${summary['final_balance']:.2f}")
    pnl = summary["total_pnl"]
    pct = summary["total_return_pct"]
    print(f"  Total P&L:       ${pnl:+.2f} ({pct:+.1f}%)")
    print(f"  Total trades:    {summary['total_trades']}")
    print(f"  Wins:            {summary['wins']}")
    print(f"  Losses:          {summary['losses']}")
    print(f"  Win rate:        {summary['win_rate']:.1%}")
    print(f"  Max drawdown:    {summary['max_drawdown']:.1%}")
    print(f"  Profit factor:   {summary['profit_factor']:.2f}")
    print(f"  Expectancy:      ${summary['expectancy']:.2f}")

    by_strat = summary["by_strategy"]
    if by_strat and isinstance(by_strat, dict):
        print("\n  By strategy:")
        for name, stats in by_strat.items():
            assert isinstance(stats, dict)
            print(
                f"    {name}: {stats['wins']}W/{stats['losses']}L,"
                f" P&L=${stats['total_pnl']:+.2f}"
            )

    if tradebook.trades:
        print(f"\n{'=' * 60}")
        print(f"TRADE LOG ({len(tradebook.trades)} trades)")
        print("=" * 60)
        for i, trade in enumerate(tradebook.trades, 1):
            c = trade.candidate
            exit_str = trade.exit_timestamp.date().isoformat() if trade.exit_timestamp else "OPEN"
            dir_str = "LONG " if c.direction.value == "bullish" else "SHORT"
            print(
                f"  {i:3d}. {trade.entry_timestamp.date().isoformat()} -> {exit_str} "
                f"{dir_str} entry=${c.entry:.0f} stop=${c.stop:.0f} "
                f"target=${c.target:.0f} RR={c.rr_ratio:.1f} "
                f"P&L=${trade.pnl:+.2f} ({trade.result})"
            )
    else:
        print("\nNo trades executed.")

    output_path = Path(args.output)
    if output_path:
        ctx = RenderContext(
            frames=frame_store,
            store=store,
            tradebook=tradebook,
            max_hold_days=bt._max_hold_days,
            window_size=bt._window_size,
        )
        renderer = InteractiveRenderer(ctx)
        renderer.render(output_path)
        print(f"\nHTML chart: {output_path}")

    if args.pickle:
        import pickle

        with open(args.pickle, "wb") as f:
            pickle.dump(result, f)
        print(f"Pickle: {args.pickle}")


def instruments_list_command(args: argparse.Namespace) -> None:
    registry_path = Path(args.registry) if args.registry else Path("instruments.yaml")
    if not registry_path.exists():
        print("No instruments registry found. Use 'instruments add' to create one.")
        return
    registry = InstrumentRegistry(registry_path)
    instruments = registry.list_all()
    if not instruments:
        print("No instruments registered.")
        return
    print(f"{'Canonical':<20} {'Class':<12} {'Description':<40} Providers")
    print("-" * 120)
    for inst in instruments:
        provs = ", ".join(f"{k}={v}" for k, v in inst.providers.items())
        print(f"{inst.canonical:<20} {inst.asset_class:<12} {inst.description:<40} {provs}")
    print(f"\nTotal: {len(instruments)} instruments")


def instruments_add_command(args: argparse.Namespace) -> None:
    registry_path = Path(args.registry) if args.registry else Path("instruments.yaml")
    registry = InstrumentRegistry(registry_path)

    providers: dict[str, str] = {}
    if args.yahoo_symbol:
        providers["yahoo"] = args.yahoo_symbol
    if args.dukascopy_symbol:
        providers["dukascopy"] = args.dukascopy_symbol
    if args.oanda_symbol:
        providers["oanda"] = args.oanda_symbol

    instr = Instrument(
        canonical=args.canonical,
        asset_class=args.asset_class,
        description=args.description,
        providers=providers,
    )
    registry.add(instr)
    registry.save(registry_path)
    print(f"Added instrument: {instr.canonical} ({instr.asset_class})")


def main() -> None:
    parser = argparse.ArgumentParser(description="MarketAtlas CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch market data")
    fetch_parser.add_argument("--symbol", required=True, help="Symbol to fetch (e.g., BTCUSDT)")
    fetch_parser.add_argument("--timeframe", required=True, help="Timeframe (e.g., 1h, 1d)")
    fetch_parser.add_argument("--start", required=True, help="Start date (ISO format)")
    fetch_parser.add_argument("--end", required=True, help="End date (ISO format)")
    fetch_parser.add_argument("--output", default="data/", help="Output directory (default: data/)")

    run_parser = subparsers.add_parser("run", help="Run a strategy backtest")
    run_parser.add_argument("--strategy", "-s", required=True, help="Strategy YAML file path")
    run_parser.add_argument("--symbol", default="BTC-USD", help="Market symbol (default: BTC-USD)")
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
