from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from marketatlas.data.providers.yahoo import YahooProvider
from marketatlas.data.types import Symbol, Timeframe


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


def main() -> None:
    parser = argparse.ArgumentParser(description="MarketAtlas CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch market data")
    fetch_parser.add_argument("--symbol", required=True, help="Symbol to fetch (e.g., BTCUSDT)")
    fetch_parser.add_argument("--timeframe", required=True, help="Timeframe (e.g., 1h, 1d)")
    fetch_parser.add_argument("--start", required=True, help="Start date (ISO format)")
    fetch_parser.add_argument("--end", required=True, help="End date (ISO format)")
    fetch_parser.add_argument(
        "--output", default="data/", help="Output directory (default: data/)"
    )

    args = parser.parse_args()

    if args.command == "fetch":
        fetch_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
