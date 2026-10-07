"""Refetch the full Dukascopy history used by the mean-reversion study.

Replaces the lost /tmp/opencode/study/00_fetch_dukascopy.py. Pulls 1d + 1w
for the 23 Dukascopy-resolvable portfolio symbols, 2003-05-04 -> 2026-09-04,
into data/study/ with page-level provider caching.

Run: poetry run python study/fetch_history.py
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from marketatlas.data.providers.dukascopy import DukascopyProvider
from marketatlas.data.providers.base import (
    FeedUnavailableError,
    NoDataAvailableError,
    SymbolNotFoundError,
)
from marketatlas.data.types import MarketData, Symbol, Timeframe

OUT = Path(__file__).resolve().parent.parent / "data" / "study"
CACHE = OUT / "page_cache"

SYMBOLS = [
    "AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADJPY",
    "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD",
    "GBPAUD", "GBPJPY", "GBPNZD", "GBPUSD",
    "NZDCAD", "NZDJPY", "NZDUSD", "USDCAD", "USDCHF",
    "XAGUSD", "XAUUSD",
]

START = datetime(2003, 5, 4, tzinfo=UTC)
END = datetime(2026, 9, 4, tzinfo=UTC)


def _filename(symbol: str, timeframe: Timeframe) -> str:
    return f"{symbol}.{timeframe.value}.parquet"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    provider = DukascopyProvider(cache_dir=CACHE)
    failures = 0
    for symbol in SYMBOLS:
        for tf in (Timeframe.D1, Timeframe.W1):
            dest = OUT / _filename(symbol, tf)
            if dest.exists():
                print(f"skip  {symbol:7} {tf.value} (exists)")
                continue
            try:
                t0 = time.time()
                data: MarketData = provider.fetch(Symbol(symbol), tf, START, END)
            except SymbolNotFoundError:
                print(f"MISS  {symbol:7} {tf.value}")
                failures += 1
                continue
            except (NoDataAvailableError, FeedUnavailableError) as exc:
                print(f"FAIL  {symbol:7} {tf.value}: {exc}")
                failures += 1
                continue
            _write_parquet(data, dest)
            first = data.candles[0].timestamp.date() if data.candles else None
            last = data.candles[-1].timestamp.date() if data.candles else None
            print(f"ok    {symbol:7} {tf.value} n={len(data.candles)} "
                  f"{first}..{last} ({time.time() - t0:.1f}s)")
            time.sleep(0.4)
    print(f"\n{'FAILURES: ' + str(failures) if failures else 'all ok'}")
    return 1 if failures else 0


def _write_parquet(data: MarketData, dest: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    ts = [c.timestamp for c in data.candles]
    table = pa.table({
        "timestamp": pa.array(ts, pa.timestamp("ns", tz="UTC")),
        "open": pa.array([c.open for c in data.candles], pa.float64()),
        "high": pa.array([c.high for c in data.candles], pa.float64()),
        "low": pa.array([c.low for c in data.candles], pa.float64()),
        "close": pa.array([c.close for c in data.candles], pa.float64()),
        "volume": pa.array([c.volume for c in data.candles], pa.float64()),
    })
    pq.write_table(table, dest)


if __name__ == "__main__":
    sys.exit(main())
