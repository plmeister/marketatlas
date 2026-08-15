from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from marketatlas.analysis.ast.instrument import TemplateGraph

from marketatlas.data.datastore import DataStore
from marketatlas.data.instrument import Instrument, InstrumentRegistry
from marketatlas.data.portfolio import (
    InstrumentDataError,
    PortfolioError,
    fetch_instrument_data,
    load_portfolio,
)
from marketatlas.data.provider_names import DEFAULT_PROVIDER_ORDER
from marketatlas.data.providers.base import DataProvider
from marketatlas.data.providers.chain import ProviderChain
from marketatlas.data.providers.dukascopy import DukascopyProvider
from marketatlas.data.providers.yahoo import YahooProvider
from marketatlas.data.types import MarketData, Symbol, Timeframe

DEFAULT_REGISTRY_PATH = Path("data/instruments.yaml")


def _registry_path(args: argparse.Namespace) -> Path:
    path = getattr(args, "registry", "") or ""
    return Path(path) if path else DEFAULT_REGISTRY_PATH


def _load_registry(args: argparse.Namespace) -> InstrumentRegistry | None:
    path = _registry_path(args)
    if not path.exists():
        return None
    return InstrumentRegistry(path)


def _make_provider(name: str, registry: InstrumentRegistry | None) -> DataProvider | None:
    if name == "yahoo":
        return YahooProvider(registry=registry)
    if name == "dukascopy":
        return DukascopyProvider(registry=registry)
    return None


def _build_chain(symbol: str, registry: InstrumentRegistry | None) -> ProviderChain:
    if registry is not None:
        inst = registry.get(symbol)
        if inst is not None:
            names = registry.get_priority(symbol)
            providers = [p for n in names if (p := _make_provider(n, registry)) is not None]
            if providers:
                return ProviderChain(providers)
        else:
            print(
                f"WARNING: '{symbol}' not found in instrument registry; " "using default providers",
                file=sys.stderr,
            )
    providers = [
        p for n in DEFAULT_PROVIDER_ORDER if (p := _make_provider(n, registry)) is not None
    ]
    return ProviderChain(providers)


def _portfolio_instrument(args: argparse.Namespace, symbol: Symbol) -> Instrument:
    registry = _load_registry(args)
    if registry is not None:
        inst = registry.get(symbol.name)
        if inst is not None:
            return inst
    return Instrument(canonical=symbol.name, asset_class="", description="")


def fetch_command(args: argparse.Namespace) -> None:
    symbol = Symbol(args.symbol)
    registry = _load_registry(args)
    provider = _build_chain(symbol.name, registry)
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
    from marketatlas.data.resample import tf_minutes
    from marketatlas.data.store import MarketStore
    from marketatlas.strategy.bundle import StrategyBundle
    from marketatlas.strategy.loader import load_strategy
    from marketatlas.strategy.strategy import Strategy
    from marketatlas.visualization.context import RenderContext
    from marketatlas.visualization.interactive import InteractiveRenderer

    if getattr(args, "instruments", ""):
        run_portfolio_command(args)
        return

    strategy_path = Path(args.strategy)
    if not strategy_path.exists():
        print(f"Error: strategy file not found: {strategy_path}", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "ab", False):
        _run_ab_test(args, strategy_path)
        return

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
    all_tfs = sorted(set([base_tf] + config_tfs), key=lambda tf: tf_minutes(tf))
    print(f"\nFetching {len(all_tfs)} timeframe(s): {', '.join(tf.value for tf in all_tfs)}")
    print(f"Range: {start.date()} to {end.date()}")
    registry = _load_registry(args)
    provider = _build_chain(symbol.name, registry)
    print("Providers: " + ", ".join(type(p).__name__ for p in provider.providers))
    datastore = DataStore(Path(args.data_dir) if args.data_dir else None)
    print(f"Data store: {datastore.base_path}")

    instrument = _portfolio_instrument(args, symbol)
    try:
        data = fetch_instrument_data(provider, datastore, instrument, all_tfs, start, end, base_tf)
    except InstrumentDataError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    fetched = data.timeframes
    resampled = data.resampled

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
            inst_str = f"{trade.instrument or '-':>12}"
            print(
                f"  {i:3d}. {inst_str} {trade.entry_timestamp.date().isoformat()} -> {exit_str} "
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


def _run_ab_test(args: argparse.Namespace, strategy_path: Path) -> None:
    """A/B test every concrete variant of a choice template (backlog 048).

    Expands the DSL's ``<a | b | c>`` template choices into one backtest per
    variant and prints a comparison. The variant's signal rules identify it
    (e.g. ``min_strength=0.3``), so template substitution is a single-source
    A/B workflow. ``--output`` writes one HTML chart per variant.
    """
    from marketatlas.analysis.ast.compiler import ASTCompiler
    from marketatlas.analysis.ast.parser import parse_with_positions
    from marketatlas.backtesting.backtester import Backtester
    from marketatlas.data.resample import tf_minutes
    from marketatlas.data.store import MarketStore
    from marketatlas.strategy.bundle import StrategyBundle
    from marketatlas.strategy.strategy import Strategy
    from marketatlas.visualization.context import RenderContext
    from marketatlas.visualization.interactive import InteractiveRenderer

    if strategy_path.suffix != ".dsl":
        print(
            "Error: --ab requires a DSL strategy file (.dsl) with template choices",
            file=sys.stderr,
        )
        sys.exit(1)

    source = strategy_path.read_text()
    try:
        analysis, _ = parse_with_positions(source, name=strategy_path.stem)
        templates = ASTCompiler.compile_templates(analysis)
    except Exception as e:
        print(f"Error compiling DSL '{strategy_path}': {e}", file=sys.stderr)
        sys.exit(1)

    if not templates:
        print("Error: DSL produced no template variants", file=sys.stderr)
        sys.exit(1)

    symbol = Symbol(args.symbol)
    base_tf = Timeframe(args.interval)
    default_start = datetime.now() - timedelta(days=730)
    start = datetime.fromisoformat(args.start) if args.start else default_start
    end = datetime.fromisoformat(args.end) if args.end else datetime.now()

    all_tfs = sorted(
        set([base_tf] + [Timeframe(tf) for tf in templates[0].config.timeframes]),
        key=lambda tf: tf_minutes(tf),
    )
    print(f"\nFetching {len(all_tfs)} timeframe(s): {', '.join(tf.value for tf in all_tfs)}")
    print(f"Range: {start.date()} to {end.date()}")
    registry = _load_registry(args)
    provider = _build_chain(symbol.name, registry)
    datastore = DataStore(Path(args.data_dir) if args.data_dir else None)
    instrument = _portfolio_instrument(args, symbol)
    try:
        data = fetch_instrument_data(provider, datastore, instrument, all_tfs, start, end, base_tf)
    except InstrumentDataError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    store = MarketStore(data.timeframes)

    print("\n" + "=" * 60)
    print(f"A/B TEST — {len(templates)} variant(s)")
    print("=" * 60)

    rows: list[tuple[TemplateGraph, Any, dict[str, object]]] = []
    for i, template in enumerate(templates, 1):
        strategy = Strategy(template.config.name, template.config)
        bundle = StrategyBundle([strategy], initial_balance=args.balance)
        bt = Backtester(store, bundle, window_size=100, max_hold_days=args.max_hold_days)
        print(f"\r  Variant {i}/{len(templates)}", end="", flush=True)
        result = bt.run()
        rows.append((template, result, result.tradebook.summary))

    print("\n")
    for i, (template, result, summary) in enumerate(rows, 1):
        label = _variant_label(template)
        pnl = summary["total_pnl"]
        pct = summary["total_return_pct"]
        print(
            f"  [{i}] {label:<40s} {summary['total_trades']:3d} trades "
            f"{summary['wins']}W/{summary['losses']}L "
            f"P&L=${pnl:+.2f} ({pct:+.1f}%)"
        )

    if args.output:
        output_path = Path(args.output)
        for i, (template, result, _) in enumerate(rows, 1):
            ctx = RenderContext(
                frames=result.frames,
                store=store,
                tradebook=result.tradebook,
                max_hold_days=args.max_hold_days,
                window_size=100,
            )
            renderer = InteractiveRenderer(ctx)
            variant_path = output_path.with_name(
                f"{output_path.stem}_v{i}{output_path.suffix}"
            )
            renderer.render(variant_path)
            print(f"HTML chart: {variant_path}")


def _variant_label(template: TemplateGraph) -> str:
    """Human label for a concrete variant: its distinguishing signal rules."""
    parts: list[str] = []
    for sc in template.config.signals:
        for k, v in sc.rules.items():
            parts.append(f"{k}={v}")
    return ", ".join(parts) if parts else "default"


def run_portfolio_command(args: argparse.Namespace) -> None:
    from marketatlas.data.resample import tf_minutes
    from marketatlas.data.store import MarketStore
    from marketatlas.strategy.loader import load_strategy

    strategy_path = Path(args.strategy)
    if not strategy_path.exists():
        print(f"Error: strategy file not found: {strategy_path}", file=sys.stderr)
        sys.exit(1)

    try:
        config = load_strategy(strategy_path)
    except Exception as e:
        print(f"Error loading strategy: {e}", file=sys.stderr)
        sys.exit(1)

    registry = _load_registry(args)
    if registry is None:
        print(
            "Error: --instruments requires an instrument registry " f"({_registry_path(args)})",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        spec = load_portfolio(Path(args.instruments), registry)
    except PortfolioError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Strategy: {config.name} v{config.version}")
    print(
        f"Portfolio: {len(spec)} instrument(s): " + ", ".join(i.canonical for i in spec.instruments)
    )

    base_tf = Timeframe(args.interval)
    default_start = datetime.now() - timedelta(days=730)
    start = datetime.fromisoformat(args.start) if args.start else default_start
    end = datetime.fromisoformat(args.end) if args.end else datetime.now()

    config_tfs = [Timeframe(tf) for tf in config.timeframes]
    all_tfs = sorted(set([base_tf] + config_tfs), key=lambda tf: tf_minutes(tf))
    print(f"\nFetching {len(all_tfs)} timeframe(s): {', '.join(tf.value for tf in all_tfs)}")
    print(f"Range: {start.date()} to {end.date()}")
    datastore = DataStore(Path(args.data_dir) if args.data_dir else None)
    print(f"Data store: {datastore.base_path}")

    loaded: list[tuple[Instrument, dict[Timeframe, MarketData]]] = []
    for instrument in spec.instruments:
        print(f"\nFetching {instrument.canonical} ({instrument.asset_class})")
        provider = _build_chain(instrument.canonical, registry)
        print("  Providers: " + ", ".join(type(p).__name__ for p in provider.providers))
        try:
            data = fetch_instrument_data(
                provider,
                datastore,
                instrument,
                all_tfs,
                start,
                end,
                base_tf,
                label=instrument.canonical,
            )
        except InstrumentDataError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        loaded.append((instrument, data.timeframes))

    if not loaded:
        print("\nError: no instrument data loaded", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"PORTFOLIO DATA ({len(loaded)} instrument(s))")
    print("=" * 60)

    from marketatlas.strategy.bundle import StrategyBundle
    from marketatlas.strategy.strategy import Strategy

    stores: dict[str, MarketStore] = {}
    pairs: list[tuple[Instrument, MarketStore]] = []
    for instrument, timeframes in loaded:
        store = MarketStore(timeframes)
        stores[instrument.canonical] = store
        pairs.append((instrument, store))
        print(
            f"  {instrument.canonical}: {len(store)} candles ({store.timeframe.value}), "
            f"{len(store.available_timeframes)} timeframe(s)"
        )

    strategy = Strategy(config.name, config)
    bundle = StrategyBundle([strategy], initial_balance=args.balance)

    from marketatlas.backtesting.portfolio import PortfolioBacktester

    bt = PortfolioBacktester(bundle, pairs, window_size=100, max_hold_days=args.max_hold_days)
    print(f"\nRunning portfolio backtest ({bt.frame_count} merged frames)...")

    def progress(cur: int, total: int) -> None:
        print(f"\r  Frame {cur}/{total}", end="", flush=True)

    result = bt.run_with_progress(progress)
    print("\n")

    summary: dict[str, object] = result.tradebook.summary
    print("=" * 60)
    print("PORTFOLIO RESULTS")
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

    by_instrument = summary["by_instrument"]
    if by_instrument and isinstance(by_instrument, dict):
        print("\n  By instrument:")
        for name, stats in by_instrument.items():
            assert isinstance(stats, dict)
            print(
                f"    {name}: {stats['wins']}W/{stats['losses']}L,"
                f" P&L=${stats['total_pnl']:+.2f}"
            )

    by_strategy = summary["by_strategy"]
    if by_strategy and isinstance(by_strategy, dict):
        print("\n  By strategy:")
        for name, stats in by_strategy.items():
            assert isinstance(stats, dict)
            print(
                f"    {name}: {stats['wins']}W/{stats['losses']}L,"
                f" P&L=${stats['total_pnl']:+.2f}"
            )

    if args.output:
        from marketatlas.visualization.portfolio import render_portfolio

        output_path = Path(args.output)
        index, charts = render_portfolio(result, stores, output_path.parent, output_path.stem)
        print(f"\nPortfolio HTML: {index}")
        print(f"Per-instrument charts: {', '.join(str(p) for p in charts)}")

    if args.pickle:
        import pickle

        with open(args.pickle, "wb") as f:
            pickle.dump(result, f)
        print(f"Pickle: {args.pickle}")


def instruments_list_command(args: argparse.Namespace) -> None:
    registry = _load_registry(args)
    if registry is None:
        print("No instruments registry found. Use 'instruments add' to create one.")
        return
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
    path = _registry_path(args)
    registry = _load_registry(args) or InstrumentRegistry()

    providers: dict[str, str] = {}
    if args.yahoo_symbol:
        providers["yahoo"] = args.yahoo_symbol
    if args.dukascopy_symbol:
        providers["dukascopy"] = args.dukascopy_symbol
    if args.oanda_symbol:
        providers["oanda"] = args.oanda_symbol

    priority = ()
    if args.provider_priority:
        priority = tuple(args.provider_priority.split(","))

    try:
        instr = Instrument(
            canonical=args.canonical,
            asset_class=args.asset_class,
            description=args.description,
            providers=providers,
            provider_priority=priority,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    registry.add(instr)
    registry.save(path)
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
