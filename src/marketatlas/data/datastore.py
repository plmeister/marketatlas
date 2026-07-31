from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from marketatlas.data.repository import MarketRepository
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


def default_store_path() -> Path:
    env = os.environ.get("MARKETATLAS_DATA_DIR")
    if env:
        return Path(env)
    return Path("~/.cache/marketatlas/data").expanduser()


class _FetchProvider(Protocol):
    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData: ...


class DataStore:
    """Persistent local store for fetched market data.

    Keyed by ``(symbol, timeframe)``; values are candles in Parquet files
    (matching the ``MarketStore`` round-trip format). A coverage query answers
    "do I have data for X from A to B?" before any network fetch is attempted.

    Files are stored as ``{symbol}.{timeframe}.parquet`` under a single base
    directory. Writes are atomic (temp file + ``os.replace``) so the store is
    safe enough for CLI use without a database.

    Coverage semantics: stored candles are treated as one contiguous range
    ``[first_timestamp, last_timestamp]``. ``has`` checks subsumption against
    that range; ``missing_ranges`` reports the leading/trailing gaps outside
    it. Interior gaps are assumed absent because stored series come from merged
    range fetches.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        self._base_path = base_path if base_path is not None else default_store_path()
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._repo = MarketRepository(self._base_path)
        self._coverage_cache: dict[tuple[Symbol, Timeframe], tuple[datetime, datetime] | None] = {}

    @property
    def base_path(self) -> Path:
        return self._base_path

    def _file_path(self, symbol: Symbol, timeframe: Timeframe) -> Path:
        return self._base_path / f"{symbol.name}.{timeframe.value}.parquet"

    def _read_candles(self, symbol: Symbol, timeframe: Timeframe) -> tuple[Candle, ...] | None:
        path = self._file_path(symbol, timeframe)
        if not path.exists():
            return None
        return self._repo.load(symbol, timeframe).candles

    def coverage(self, symbol: Symbol, timeframe: Timeframe) -> tuple[datetime, datetime] | None:
        key = (symbol, timeframe)
        if key not in self._coverage_cache:
            path = self._file_path(symbol, timeframe)
            if not path.exists():
                self._coverage_cache[key] = None
            else:
                table = pq.read_table(path, columns=["timestamp"])
                timestamps = table.column("timestamp").to_pylist()
                if not timestamps:
                    self._coverage_cache[key] = None
                else:
                    naive = (_as_naive(min(timestamps)), _as_naive(max(timestamps)))
                    self._coverage_cache[key] = naive
        return self._coverage_cache[key]

    def has(self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime) -> bool:
        cover = self.coverage(symbol, timeframe)
        if cover is None:
            return False
        first, last = cover
        return _as_naive(start) >= first and _as_naive(end) <= last

    def missing_ranges(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> tuple[tuple[datetime, datetime], ...]:
        cover = self.coverage(symbol, timeframe)
        if cover is None:
            return ((start, end),)
        first, last = cover
        start_naive = _as_naive(start)
        end_naive = _as_naive(end)
        missing: list[tuple[datetime, datetime]] = []
        if start_naive < first:
            missing.append((_with_tz(start_naive, start), _with_tz(first, start)))
        if end_naive > last:
            missing.append((_with_tz(last, end), _with_tz(end_naive, end)))
        return tuple(missing)

    def get(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData | None:
        candles = self._read_candles(symbol, timeframe)
        if not candles:
            return None
        start_naive = _as_naive(start)
        end_naive = _as_naive(end)
        clipped = tuple(c for c in candles if start_naive <= _as_naive(c.timestamp) <= end_naive)
        if not clipped:
            return None
        return MarketData(symbol=symbol, timeframe=timeframe, candles=clipped)

    def put(self, market_data: MarketData) -> None:
        if not market_data.candles:
            return
        symbol = market_data.symbol
        timeframe = market_data.timeframe
        normalized = tuple(_normalize_candle(c) for c in market_data.candles)
        existing = self._read_candles(symbol, timeframe) or ()
        merged = _merge_candles(existing, normalized)
        if not merged:
            return

        table = pa.table(
            {
                "timestamp": [c.timestamp for c in merged],
                "open": [c.open for c in merged],
                "high": [c.high for c in merged],
                "low": [c.low for c in merged],
                "close": [c.close for c in merged],
                "volume": [c.volume for c in merged],
            }
        )
        path = self._file_path(symbol, timeframe)
        self._write_table_atomic(path, table)
        self._coverage_cache[(symbol, timeframe)] = (
            _as_naive(merged[0].timestamp),
            _as_naive(merged[-1].timestamp),
        )

    def fetch_or_get(
        self,
        provider: _FetchProvider,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData:
        """Return cached data if covered; otherwise fetch only uncovered gaps and merge."""
        cached = self.get(symbol, timeframe, start, end)
        parts: list[tuple[Candle, ...]] = []
        if cached is not None:
            parts.append(cached.candles)

        missing = self.missing_ranges(symbol, timeframe, start, end)
        fetched_parts: list[tuple[Candle, ...]] = []
        for gap_start, gap_end in missing:
            md = provider.fetch(symbol, timeframe, gap_start, gap_end)
            normalized = tuple(_normalize_candle(c) for c in md.candles)
            fetched_parts.append(normalized)
            parts.append(normalized)

        combined = _merge_candles(*(p for p in parts))
        if fetched_parts:
            self.put(MarketData(symbol=symbol, timeframe=timeframe, candles=combined))
        return MarketData(symbol=symbol, timeframe=timeframe, candles=combined)

    def cached_symbols(self) -> list[Symbol]:
        symbols: set[str] = set()
        for file in self._base_path.glob("*.parquet"):
            symbols.add(file.name.split(".")[0])
        return sorted((Symbol(name=s) for s in symbols), key=lambda s: s.name)

    def cached_timeframes(self, symbol: Symbol) -> list[Timeframe]:
        timeframes: list[Timeframe] = []
        for tf in Timeframe:
            if self._file_path(symbol, tf).exists():
                timeframes.append(tf)
        return timeframes

    def _write_table_atomic(self, path: Path, table: pa.Table) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        os.close(fd)
        try:
            pq.write_table(table, tmp_path)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def _as_naive(ts: datetime) -> datetime:
    return ts.replace(tzinfo=None)


def _utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _with_tz(naive: datetime, reference: datetime) -> datetime:
    if reference.tzinfo is None:
        return naive
    return naive.replace(tzinfo=reference.tzinfo)


def _normalize_candle(candle: Candle) -> Candle:
    return Candle(
        timestamp=_utc(candle.timestamp),
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )


def _merge_candles(*groups: tuple[Candle, ...]) -> tuple[Candle, ...]:
    by_ts: dict[datetime, Candle] = {}
    for group in groups:
        for candle in group:
            by_ts[_as_naive(candle.timestamp)] = candle
    return tuple(sorted(by_ts.values(), key=lambda c: _as_naive(c.timestamp)))
