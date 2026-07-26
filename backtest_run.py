#!/usr/bin/env python3
"""Backtest runner — full pipeline with real BTC-USD data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from marketatlas.backtesting.backtester import Backtester
from marketatlas.data.providers.yahoo import YahooProvider
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Symbol, Timeframe
from marketatlas.strategy.bundle import StrategyBundle
from marketatlas.strategy.loader import load_strategy
from marketatlas.strategy.strategy import Strategy
from marketatlas.visualization.context import RenderContext
from marketatlas.visualization.interactive import InteractiveRenderer

STRATEGY_YAML = """\
strategy:
  name: pullback_4swing
  version: "1.0"

analyzers:
  - type: EMAAnalyzer
    params:
      period: 20
  - type: EMAAnalyzer
    params:
      period: 50
  - type: ATRAnalyzer
    params:
      period: 14
  - type: TrendAnalyzer
    params:
      fast_key: ema_20
      slow_key: ema_50
      atr_key: atr_14
  - type: SwingStructureAnalyzer
    params:
      atr_key: atr_14
      lookback: 50
      min_swing_atr: 1.5
  - type: SupportResistanceAnalyzer
    params:
      atr_key: atr_14
      swing_key: swing
  - type: FourSwingPullbackDetector
    params:
      trend_key: trend
      swing_key: swing
      atr_key: atr_14
      confirmation_min_body_pct: 0.3
      confirmation_min_volume_ratio: 0.8
      max_deviation_pct: 0.25

signals:
  - type: PullbackSignal
    requires:
      - four_swing_pullback
      - trend
      - atr_14
    rules:
      pullback_key: four_swing_pullback
      trend_key: trend
      atr_key: atr_14
      min_strength: 0.3

risk:
  algorithm: basic
  params:
    risk_pct: 1.0
    min_rr: 2.0
    max_rr: 4.0
    max_stop_atr: 3.0
    max_hold_days: 10
    avoid_srxing: true
    slippage_pct: 0.1
"""


def main() -> None:
    print("=" * 60)
    print("MarketAtlas Backtest — BTC-USD D1")
    print("=" * 60)

    # Load strategy
    config_path = Path("/tmp/pullback_4swing.yaml")
    config_path.write_text(STRATEGY_YAML)
    config = load_strategy(config_path)
    strategy = Strategy("pullback_4swing", config)
    bundle = StrategyBundle([strategy], initial_balance=10000.0)

    print(f"\nStrategy: {config.name} v{config.version}")
    print(f"Analyzers: {len(config.analyzers)}")
    print(f"Signals: {len(config.signals)}")

    # Fetch real data
    print("\nFetching BTC-USD daily data (2023-2025)...")
    provider = YahooProvider()
    market_data = provider.fetch(
        Symbol("BTC-USD"), Timeframe.D1,
        datetime(2023, 1, 1), datetime(2025, 1, 1),
    )
    store = MarketStore(market_data)
    print(f"Data: {len(store)} candles")
    print(f"Range: {store[0].timestamp.date()} to {store[-1].timestamp.date()}")
    print(f"Price: ${store[0].close:.0f} -> ${store[-1].close:.0f}")

    # Run backtest
    bt = Backtester(store, bundle, window_size=100, max_hold_days=10)

    # Debug: scan frames for pullback status
    from marketatlas.data.view import MarketView as MV
    from marketatlas.facts.pattern import PullbackFact, PullbackStatus

    detected = 0
    confirmed = 0
    invalidated_reasons: dict[str, int] = {}
    for cursor in range(100, len(store)):
        view = MV(store, cursor, 100)
        facts = bundle.graph.run(view)
        pb = facts.get((PullbackFact, "four_swing_pullback"))
        if isinstance(pb, PullbackFact):
            if pb.status == PullbackStatus.DETECTED:
                detected += 1
            elif pb.status == PullbackStatus.CONFIRMED:
                confirmed += 1
                print(f"  CONFIRMED at cursor {cursor} "
                      f"({store[cursor].timestamp.date()}) "
                      f"pattern={pb.swing_pattern} "
                      f"conf_str={pb.confirmation_strength:.2f}")
            elif pb.status == PullbackStatus.INVALIDATED:
                # Get the evidence reason
                for e in pb.evidence:
                    if "No pullback" in e.text or "invalidated" in e.text.lower():
                        reason = e.text.split("—")[-1].strip() if "—" in e.text else e.text
                        invalidated_reasons[reason] = invalidated_reasons.get(reason, 0) + 1

    print(f"\n  Pullback scan: {detected} DETECTED, {confirmed} CONFIRMED")
    if invalidated_reasons:
        print("  Invalidation reasons:")
        for reason, count in sorted(invalidated_reasons.items(), key=lambda x: -x[1]):
            print(f"    {count:4d}x {reason}")

    print(f"\nRunning backtest ({bt.frame_count} frames)...")
    frame_store, tradebook = bt.run_with_progress(
        lambda cur, total: print(f"\r  Frame {cur}/{total}", end="", flush=True)
    )
    print("\n")

    # Results
    summary = tradebook.summary
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Initial balance: ${summary['initial_balance']:.2f}")
    print(f"  Final balance:   ${summary['final_balance']:.2f}")
    pnl = summary['total_pnl']
    pct = summary['total_return_pct']
    print(f"  Total P&L:       ${pnl:+.2f} ({pct:+.1f}%)")
    print(f"  Total trades:    {summary['total_trades']}")
    print(f"  Wins:            {summary['wins']}")
    print(f"  Losses:          {summary['losses']}")
    print(f"  Win rate:        {summary['win_rate']:.1%}")
    print(f"  Max drawdown:    {summary['max_drawdown']:.1%}")

    by_strat = summary["by_strategy"]
    if by_strat:
        assert isinstance(by_strat, dict)
        print("\n  By strategy:")
        for name, stats in by_strat.items():
            print(f"    {name}: {stats['wins']}W/{stats['losses']}L, P&L=${stats['total_pnl']:+.2f}")

    # Trade details
    if tradebook.trades:
        print(f"\n{'=' * 60}")
        print(f"TRADE LOG ({len(tradebook.trades)} trades)")
        print("=" * 60)
        for i, trade in enumerate(tradebook.trades, 1):
            c = trade.candidate
            exit_str = (
                trade.exit_timestamp.date().isoformat()
                if trade.exit_timestamp
                else "OPEN"
            )
            dir_str = "LONG " if c.direction.value == "bullish" else "SHORT"
            print(
                f"  {i:3d}. {trade.entry_timestamp.date().isoformat()} -> {exit_str} "
                f"{dir_str} entry=${c.entry:.0f} stop=${c.stop:.0f} "
                f"target=${c.target:.0f} RR={c.rr_ratio:.1f} "
                f"P&L=${trade.pnl:+.2f} ({trade.result})"
            )
    else:
        print("\nNo trades executed.")

    # Evidence samples
    if frame_store and tradebook.trades:
        print(f"\n{'=' * 60}")
        print("SAMPLE EVIDENCE (first trade's frame)")
        print("=" * 60)
        first_entry = tradebook.trades[0].entry_timestamp
        for frame in frame_store:
            if frame.timestamp == first_entry:
                for entry in frame.evidence[:8]:
                    print(f"  [{entry.level.value:7s}] {entry.source}: {entry.text}")
                break

    # HTML chart output
    html_path = Path("/tmp/backtest_result.html")
    ctx = RenderContext(
        frames=frame_store, store=store, tradebook=tradebook,
        max_hold_days=bt._max_hold_days,
    )
    renderer = InteractiveRenderer(ctx)
    renderer.render(html_path)
    print(f"\nHTML chart written to: {html_path}")

    print()


if __name__ == "__main__":
    main()
