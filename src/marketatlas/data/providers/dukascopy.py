from __future__ import annotations

import struct
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from marketatlas.data.instrument import InstrumentRegistry
from marketatlas.data.providers.base import (
    DataProvider,
    NoDataAvailableError,
    RateLimitError,
    UnsupportedTimeframeError,
)
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


class DukascopyProvider(DataProvider):
    _BASE_URL = "https://datafeed.dukascopy.com/datafeed/{instrument}/{year}/{month:02d}/{day:02d}{hour:02d}{min:02d}_ohlcv_{tf_minutes}.bi5"

    _TIMEFRAME_MINUTES = {
        Timeframe.M1: 1,
        Timeframe.M5: 5,
        Timeframe.M15: 15,
        Timeframe.M30: 30,
        Timeframe.H1: 60,
        Timeframe.H4: 240,
    }

    _RECORD_FORMAT = struct.Struct(">Ifffff")
    _RECORD_SIZE = _RECORD_FORMAT.size

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        registry: InstrumentRegistry | None = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._registry = registry

    def _resolve_symbol(self, symbol: Symbol) -> str:
        if self._registry is None:
            return symbol.name
        dukas = self._registry.get_symbol(symbol.name, "dukascopy")
        if dukas is not None:
            return dukas
        return symbol.name

    def _timeframe_minutes(self, symbol: Symbol, timeframe: Timeframe) -> int:
        tf_min = self._TIMEFRAME_MINUTES.get(timeframe)
        if tf_min is None:
            raise UnsupportedTimeframeError(symbol, timeframe)
        return tf_min

    def _cache_path(
        self, symbol: str, timeframe: Timeframe, year: int, month: int, day: int
    ) -> Path | None:
        if self._cache_dir is None:
            return None
        path = (
            self._cache_dir
            / "dukascopy"
            / symbol
            / timeframe.value
            / str(year)
            / f"{month:02d}"
            / f"{day:02d}.bi5"
        )
        return path

    def _parse_bi5(self, data: bytes, date: datetime) -> list[Candle]:
        candles: list[Candle] = []
        offset = 0
        while offset + self._RECORD_SIZE <= len(data):
            record = data[offset : offset + self._RECORD_SIZE]
            (
                sec_offset,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
            ) = self._RECORD_FORMAT.unpack(record)

            ts = date.replace(tzinfo=UTC) + timedelta(seconds=sec_offset)

            candles.append(
                Candle(
                    timestamp=ts,
                    open=float(open_price),
                    high=float(high_price),
                    low=float(low_price),
                    close=float(close_price),
                    volume=float(volume),
                )
            )
            offset += self._RECORD_SIZE

        return candles

    def _write_cache(self, path: Path, compressed_data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(compressed_data)

    def _read_cache(self, path: Path) -> bytes | None:
        if path.exists():
            return path.read_bytes()
        return None

    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData:
        instrument = self._resolve_symbol(symbol)
        tf_minutes = self._timeframe_minutes(symbol, timeframe)

        all_candles: list[Candle] = []

        current = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end.replace(hour=0, minute=0, second=0, microsecond=0)

        while current <= end_date:
            year = current.year
            month = current.month
            day = current.day

            cache_path = self._cache_path(instrument, timeframe, year, month, day)
            if cache_path is not None:
                cached = self._read_cache(cache_path)
                if cached is not None:
                    day_candles = self._parse_bi5(zlib.decompress(cached), current)
                    filtered = [c for c in day_candles if start <= c.timestamp <= end]
                    all_candles.extend(filtered)
                    current += timedelta(days=1)
                    continue

            try:
                compressed = self._fetch_day_raw(instrument, year, month, day, tf_minutes)
            except NoDataAvailableError:
                current += timedelta(days=1)
                continue

            if cache_path is not None:
                self._write_cache(cache_path, compressed)
            decompressed = zlib.decompress(compressed)

            day_candles = self._parse_bi5(decompressed, current)
            filtered = [c for c in day_candles if start <= c.timestamp <= end]
            all_candles.extend(filtered)

            current += timedelta(days=1)

        if not all_candles:
            raise NoDataAvailableError(symbol, timeframe)

        return MarketData(symbol=symbol, timeframe=timeframe, candles=tuple(all_candles))

    def _fetch_day_raw(
        self, instrument: str, year: int, month: int, day: int, tf_minutes: int
    ) -> bytes:
        url = self._BASE_URL.format(
            instrument=instrument,
            year=year,
            month=month,
            day=day,
            hour=0,
            min=0,
            tf_minutes=tf_minutes,
        )

        for attempt in range(self._max_retries):
            try:
                with urlopen(url, timeout=30) as resp:
                    compressed = cast(bytes, resp.read())
                return compressed
            except HTTPError as e:
                if e.code == 429:
                    if attempt < self._max_retries - 1:
                        import time
                        time.sleep(self._retry_delay * (attempt + 1))
                        continue
                    raise RateLimitError(
                        f"Dukascopy rate limited after {self._max_retries} attempts"
                    ) from e
                if e.code == 404:
                    raise NoDataAvailableError(
                        Symbol(instrument),
                        Timeframe.H1,
                    ) from e
                raise
            except URLError as e:
                if attempt < self._max_retries - 1:
                    import time
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue
                raise NoDataAvailableError(
                    Symbol(instrument),
                    Timeframe.H1,
                ) from e

        raise NoDataAvailableError(Symbol(instrument), Timeframe.H1)

    def supported_symbols(self) -> list[Symbol]:
        return []
