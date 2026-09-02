from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from marketatlas.analysis.ast.instrument import TemplateGraph
    from marketatlas.data.store import MarketStore

from marketatlas.cli.formatting import _ab_row
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
from marketatlas.data.providers.registry import get as get_provider_cls
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
    from marketatlas.cli import DukascopyProvider, YahooProvider

    if name == "yahoo":
        return YahooProvider(registry=registry)
    if name == "dukascopy":
        return DukascopyProvider(registry=registry)
    cls = get_provider_cls(name)
    if cls is not None:
        return cls(registry=registry)  # type: ignore[call-arg]
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

    import pyarrow as pa
    import pyarrow.parquet as pq

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

    if getattr(args, "instruments", ""):
        if getattr(args, "ab", False):
            _run_portfolio_ab_test(args, Path(args.strategy))
            return
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
    tradebook = result.tradebook
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

    monthly = tradebook.monthly_summary()
    if monthly:
        print("\n  Monthly breakdown (by exit month):")
        for month, stats in monthly.items():
            assert isinstance(stats, dict)
            print(
                f"    {month}: {stats['trades']:3d} trades,"
                f" {stats['wins']}W/{stats['losses']}L,"
                f" P&L=${stats['total_pnl']:+.2f},"
                f" growth={stats.get('growth_pct', 0.0):+.2f}%"
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
        from marketatlas.frames.output import AnalysisOutput
        from marketatlas.visualization.interactive import InteractiveRenderer

        output = AnalysisOutput.from_backtest_result(result)
        renderer = InteractiveRenderer(output)
        renderer.render(output_path)
        print(f"\nHTML chart: {output_path}")

    if args.pickle:
        import pickle

        with open(args.pickle, "wb") as f:
            pickle.dump(result, f)
        print(f"Pickle: {args.pickle}")


def _load_ab_stores(
    args: argparse.Namespace,
    templates: tuple[TemplateGraph, ...],
    instruments: list[Instrument],
    *,
    fail_fast: bool,
) -> tuple[list[tuple[Instrument, MarketStore]], datetime, datetime]:
    """Fetch/store setup shared by the single-symbol and portfolio ``--ab`` paths."""
    from marketatlas.data.resample import tf_minutes
    from marketatlas.data.store import MarketStore

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
    datastore = DataStore(Path(args.data_dir) if args.data_dir else None)
    print(f"Data store: {datastore.base_path}")

    pairs: list[tuple[Instrument, MarketStore]] = []
    for instrument in instruments:
        canonical = instrument.canonical
        provider = _build_chain(canonical, registry)
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
                label=canonical,
            )
        except InstrumentDataError as e:
            if fail_fast:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        pairs.append((instrument, MarketStore(data.timeframes)))
    return pairs, start, end


def _render_ab_variants(
    output_arg: str,
    templates: tuple[TemplateGraph, ...],
    rows: list[tuple[TemplateGraph, Any]],
    stores: Mapping[str, MarketStore],
    single_canonical: str | None,
) -> list[Path]:
    """Write the A/B output tree: one directory per variant slug (backlog 080)."""
    from marketatlas.analysis.ast.variant import variant_identity, variant_slugs
    from marketatlas.frames.output import AnalysisOutput, PortfolioOutput
    from marketatlas.visualization.interactive import InteractiveRenderer
    from marketatlas.visualization.portfolio import (
        render_ab_index,
        render_per_instrument_charts,
    )

    output_path = Path(output_arg)
    root = output_path.parent / output_path.stem if output_path.suffix else output_path
    written: list[Path] = []
    outputs: list[tuple[TemplateGraph, PortfolioOutput]] = []
    for template, result in rows:
        if single_canonical is not None:
            single = AnalysisOutput.from_backtest_result(result)
            output = PortfolioOutput(
                summary=single.summary,
                by_instrument={single_canonical: single.summary},
                outputs={single_canonical: single},
                monthly={},
                instruments=(single_canonical,),
                window_size=single.window_size,
                max_hold_days=single.max_hold_days,
                title=single_canonical,
            )
        else:
            output = PortfolioOutput.from_portfolio_result(result, stores)
        outputs.append((template, output))
    for (_, output), slug in zip(outputs, variant_slugs(templates)):
        variant_dir = root / slug
        if single_canonical is not None:
            chart = variant_dir / f"{output_path.stem}.html"
            InteractiveRenderer(output.outputs[single_canonical]).render(chart)
            written.append(chart)
        else:
            written.extend(
                render_per_instrument_charts(output, variant_dir, stem="portfolio")
            )
        print(f"HTML chart: {variant_dir}")

    if single_canonical is not None:
        chart_name = f"{output_path.stem}.html"
        instruments = [single_canonical]
    else:
        chart_name = "portfolio.{canonical}.html"
        instruments = None
    index = render_ab_index(
        [(variant_identity(template), output) for template, output in outputs],
        root,
        stem="ab",
        chart_name=chart_name,
        instruments=instruments,
    )
    written.append(index)
    print(f"A/B index: {index}")
    return written


def _run_ab_test(args: argparse.Namespace, strategy_path: Path) -> None:
    """A/B test every concrete variant of a choice template (backlog 048)."""
    from marketatlas.analysis.ast.variant import variant_labels
    from marketatlas.backtesting.backtester import Backtester
    from marketatlas.strategy.bundle import StrategyBundle
    from marketatlas.strategy.strategy import Strategy

    templates = _compile_ab_templates(args, strategy_path)

    symbol = Symbol(args.symbol)
    instrument = _portfolio_instrument(args, symbol)
    pairs, _, _ = _load_ab_stores(args, templates, [instrument], fail_fast=True)
    store = pairs[0][1]

    print("\n" + "=" * 60)
    print(f"A/B TEST — {len(templates)} variant(s)")
    print("=" * 60)

    rows: list[tuple[TemplateGraph, Any]] = []
    for i, template in enumerate(templates, 1):
        strategy = Strategy(template.config.name, template.config)
        bundle = StrategyBundle([strategy], initial_balance=args.balance)
        bt = Backtester(store, bundle, window_size=100, max_hold_days=args.max_hold_days)
        print(f"\r  Variant {i}/{len(templates)}", end="", flush=True)
        result = bt.run()
        rows.append((template, result))

    print("\n")
    labels = variant_labels(templates)
    for i, ((_, result), label) in enumerate(zip(rows, labels), 1):
        print(f"  [{i}] {_ab_row(label, result.tradebook.summary)}")

    if args.output:
        written = _render_ab_variants(
            args.output,
            templates,
            rows,
            {instrument.canonical: store},
            single_canonical=instrument.canonical,
        )
        print(f"\nA/B charts ({len(written)} file(s)): {written[0].parent}")


def _run_portfolio_ab_test(args: argparse.Namespace, strategy_path: Path) -> None:
    """Portfolio A/B: one portfolio backtest per concrete variant (backlog 079)."""
    from marketatlas.analysis.ast.variant import variant_labels
    from marketatlas.backtesting.portfolio import PortfolioBacktester
    from marketatlas.strategy.bundle import StrategyBundle
    from marketatlas.strategy.strategy import Strategy

    templates = _compile_ab_templates(args, strategy_path)

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

    print(
        f"Portfolio: {len(spec)} instrument(s): " + ", ".join(i.canonical for i in spec.instruments)
    )

    pairs, _, _ = _load_ab_stores(args, templates, list(spec.instruments), fail_fast=False)
    if not pairs:
        print("\nError: no instrument data loaded", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"A/B TEST (PORTFOLIO) — {len(templates)} variant(s)")
    print("=" * 60)

    results: list[tuple[TemplateGraph, Any]] = []
    for i, template in enumerate(templates, 1):
        strategy = Strategy(template.config.name, template.config)
        bundle = StrategyBundle([strategy], initial_balance=args.balance)
        bt = PortfolioBacktester(bundle, pairs, window_size=100, max_hold_days=args.max_hold_days)
        print(f"\r  Variant {i}/{len(templates)}", end="", flush=True)
        result = bt.run()
        results.append((template, result))

    print("\n")
    labels = variant_labels(templates)
    for i, ((_, result), label) in enumerate(zip(results, labels), 1):
        print(f"  [{i}] {_ab_row(label, result.tradebook.summary)}")

    if args.output:
        stores = {inst.canonical: store for inst, store in pairs}
        written = _render_ab_variants(
            args.output, templates, results, stores, single_canonical=None
        )
        print(f"\nA/B charts ({len(written)} file(s)): {written[0].parent}")


def _compile_ab_templates(
    args: argparse.Namespace, strategy_path: Path
) -> tuple[TemplateGraph, ...]:
    """Parse and expand a DSL strategy into concrete template variants."""
    from marketatlas.analysis.ast.compiler import ASTCompiler
    from marketatlas.analysis.ast.parser import parse_with_positions

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
    return templates


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

    from marketatlas.frames.output import PortfolioOutput

    output = PortfolioOutput.from_portfolio_result(result, stores)
    summary = output.summary
    print("=" * 60)
    print("PORTFOLIO RESULTS")
    print("=" * 60)
    print(f"  Initial balance: ${summary.initial_balance:.2f}")
    print(f"  Final balance:   ${summary.final_balance:.2f}")
    print(f"  Total P&L:       ${summary.total_pnl:+.2f} ({summary.total_return_pct:+.1f}%)")
    print(f"  Total trades:    {summary.total_trades}")
    print(f"  Wins:            {summary.wins}")
    print(f"  Losses:          {summary.losses}")
    print(f"  Win rate:        {summary.win_rate:.1%}")
    print(f"  Max drawdown:    {summary.max_drawdown:.1%}")
    print(f"  Profit factor:   {summary.profit_factor:.2f}")

    by_instrument = summary.to_dict().get("by_instrument")
    if by_instrument and isinstance(by_instrument, dict):
        print("\n  By instrument:")
        for name, stats in by_instrument.items():
            assert isinstance(stats, dict)
            print(
                f"    {name}: {stats['wins']}W/{stats['losses']}L,"
                f" P&L=${stats['total_pnl']:+.2f}"
            )

    by_strategy = summary.to_dict().get("by_strategy")
    if by_strategy and isinstance(by_strategy, dict):
        print("\n  By strategy:")
        for name, stats in by_strategy.items():
            assert isinstance(stats, dict)
            print(
                f"    {name}: {stats['wins']}W/{stats['losses']}L,"
                f" P&L=${stats['total_pnl']:+.2f}"
            )

    monthly = output.monthly
    if monthly:
        print("\n  Monthly breakdown (by exit month):")
        for month, stats in monthly.items():
            assert isinstance(stats, dict)
            print(
                f"    {month}: {stats['trades']:3d} trades,"
                f" {stats['wins']}W/{stats['losses']}L,"
                f" P&L=${stats['total_pnl']:+.2f},"
                f" growth={stats.get('growth_pct', 0.0):+.2f}%"
            )

    if args.output:
        from marketatlas.visualization.portfolio import render_portfolio

        output_path = Path(args.output)
        index, charts = render_portfolio(output, output_path.parent, output_path.stem)
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
