from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


class MarketRepository:
    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    def list_symbols(self) -> list[Symbol]:
        symbols: set[str] = set()
        for file in self._base_path.glob("*.parquet"):
            symbol_name = file.name.split(".")[0]
            symbols.add(symbol_name)
        return sorted((Symbol(name=s) for s in symbols), key=lambda s: s.name)

    def load(self, symbol: Symbol, timeframe: Timeframe) -> MarketData:
        path = self._base_path / f"{symbol.name}.{timeframe.value}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"No data file for {symbol.name} {timeframe.value}: {path}")

        table = pq.read_table(path)  # type: ignore[no-untyped-call]
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(table.column_names)):
            missing = required - set(table.column_names)
            raise ValueError(f"Malformed Parquet: missing columns {missing}")

        timestamps = table.column("timestamp").to_pylist()
        opens = table.column("open").to_pylist()
        highs = table.column("high").to_pylist()
        lows = table.column("low").to_pylist()
        closes = table.column("close").to_pylist()
        volumes = table.column("volume").to_pylist()

        candles = tuple(
            Candle(
                timestamp=t,
                open=o,
                high=h,
                low=lo,
                close=c,
                volume=v,
            )
            for t, o, h, lo, c, v in zip(timestamps, opens, highs, lows, closes, volumes)
        )

        return MarketData(symbol=symbol, timeframe=timeframe, candles=candles)
