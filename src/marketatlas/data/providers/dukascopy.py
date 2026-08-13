from __future__ import annotations

import json
import random
import string
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from marketatlas.data.instrument import InstrumentRegistry
from marketatlas.data.providers.base import (
    DataProvider,
    FeedUnavailableError,
    NoDataAvailableError,
    RateLimitError,
    UnsupportedTimeframeError,
)
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


def _to_dukascopy_instrument(name: str) -> str:
    """Canonical FX code -> dukascopy slash format (EURUSD -> EUR/USD).

    The json3 API rejects bare codes with ``[null]``; a 6-letter canonical
    (or a string already containing ``/``) maps to ``BASE/QUOTE``, anything
    else passes through untouched.
    """
    if "/" in name:
        return name
    if len(name) == 6 and name.isalpha():
        return f"{name[:3]}/{name[3:]}"
    return name


class DukascopyProvider(DataProvider):
    """Dukascopy data via the freeserv chart/json3 web API.

    Unlike the classic ``*.bi5`` binary feed (unreachable from many hosts),
    the chart API is reachable with a browser-ish ``User-Agent``/``Referer``.
    Rows arrive as ``[ms, open, high, low, close, volume]`` JSONP; forward
    pagination advances ``last_update`` to the last returned row timestamp.
    """

    _BASE_URL = "https://freeserv.dukascopy.com/2.0/index.php"

    _INTERVAL = {
        Timeframe.M1: "1MIN",
        Timeframe.M5: "5MIN",
        Timeframe.M15: "15MIN",
        Timeframe.M30: "30MIN",
        Timeframe.H1: "1HOUR",
        Timeframe.H4: "4HOUR",
        Timeframe.D1: "1DAY",
        Timeframe.W1: "1WEEK",
    }

    _PAGE_LIMIT: int = 30000
    """Max rows per page. Instance-overridable (tests shrink it)."""

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        ),
        "Host": "freeserv.dukascopy.com",
        "Referer": "https://freeserv.dukascopy.com/2.0/",
    }

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_retries: int = 5,
        retry_delay: float = 1.0,
        request_timeout: float = 60.0,
        registry: InstrumentRegistry | None = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._request_timeout = request_timeout
        self._registry = registry

    def _resolve_symbol(self, symbol: Symbol) -> str:
        if self._registry is not None:
            dukas = self._registry.get_symbol(symbol.name, "dukascopy")
            if dukas is not None:
                return dukas
        return _to_dukascopy_instrument(symbol.name)

    def _interval(self, symbol: Symbol, timeframe: Timeframe) -> str:
        interval = self._INTERVAL.get(timeframe)
        if interval is None:
            raise UnsupportedTimeframeError(symbol, timeframe)
        return interval

    def _cache_path(self, instrument: str, timeframe: Timeframe, cursor_ms: int) -> Path | None:
        if self._cache_dir is None:
            return None
        return (
            self._cache_dir
            / "dukascopy"
            / instrument
            / timeframe.value
            / f"{cursor_ms}.json"
        )

    def _write_cache(self, path: Path, rows: list[list[float]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")

    def _read_cache(self, path: Path) -> list[list[float]] | None:
        if path.exists():
            return cast(list[list[float]], json.loads(path.read_text(encoding="utf-8")))
        return None

    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData:
        instrument = self._resolve_symbol(symbol)
        interval = self._interval(symbol, timeframe)

        start = start.astimezone(UTC)
        end = end.astimezone(UTC)

        all_candles: list[Candle] = []
        cursor_ms = int(start.timestamp() * 1000)
        first_page = True

        while True:
            rows = self._fetch_page(instrument, timeframe, interval, cursor_ms)

            # The feed anchors at last_update and may repeat the boundary row.
            if not first_page and rows and rows[0][0] == cursor_ms:
                rows = rows[1:]
            first_page = False

            if not rows:
                break

            end_ms = int(end.timestamp() * 1000)
            reached_end = False
            for row in rows:
                row_ms = int(row[0])
                if row_ms > end_ms:
                    reached_end = True
                    break
                if row_ms >= cursor_ms:
                    _, open_p, high_p, low_p, close_p, volume = row
                    all_candles.append(
                        Candle(
                            timestamp=datetime.fromtimestamp(row_ms / 1000, tz=UTC),
                            open=float(open_p),
                            high=float(high_p),
                            low=float(low_p),
                            close=float(close_p),
                            volume=float(volume),
                        )
                    )

            cursor_ms = int(rows[-1][0])
            if reached_end or len(rows) < self._PAGE_LIMIT:
                break

        if not all_candles:
            raise NoDataAvailableError(symbol, timeframe)

        return MarketData(symbol=symbol, timeframe=timeframe, candles=tuple(all_candles))

    def _fetch_page(
        self,
        instrument: str,
        timeframe: Timeframe,
        interval: str,
        cursor_ms: int,
    ) -> list[list[float]]:
        cache_path = self._cache_path(instrument, timeframe, cursor_ms)
        if cache_path is not None:
            cached = self._read_cache(cache_path)
            if cached is not None:
                return cached

        url = self._build_url(instrument, interval, cursor_ms)

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                rows = self._request(url)
                if cache_path is not None:
                    self._write_cache(cache_path, rows)
                return rows
            except HTTPError as e:
                if e.code == 429:
                    if attempt < self._max_retries - 1:
                        time.sleep(self._retry_delay * (attempt + 1))
                        last_error = e
                        continue
                    raise RateLimitError(
                        f"Dukascopy rate limited after {self._max_retries} attempts"
                    ) from e
                if e.code == 404:
                    raise NoDataAvailableError(
                        Symbol(instrument),
                        timeframe,
                    ) from e
                if e.code == 503:
                    if attempt < self._max_retries - 1:
                        time.sleep(self._retry_delay * (attempt + 1))
                        last_error = e
                        continue
                    raise FeedUnavailableError(
                        f"Dukascopy feed unreachable (HTTP {e.code}) for "
                        f"{instrument} {timeframe.value} after {self._max_retries} attempts"
                    ) from e
                raise
            except URLError as e:
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
                    last_error = e
                    continue
                raise FeedUnavailableError(
                    f"Dukascopy feed unreachable (network error) for "
                    f"{instrument} {timeframe.value} after {self._max_retries} attempts"
                ) from e

        raise FeedUnavailableError(
            f"Dukascopy feed unreachable for {instrument} {timeframe.value}"
        ) from last_error

    def _build_url(self, instrument: str, interval: str, cursor_ms: int) -> str:
        jsonp = "_callbacks____" + "".join(
            random.choices(string.ascii_letters + string.digits, k=9)
        )
        query = urlencode(
            {
                "path": "chart/json3",
                "instrument": instrument,
                "interval": interval,
                "offer_side": "B",
                "time_direction": "N",
                "last_update": str(int(cursor_ms)),
                "limit": str(self._PAGE_LIMIT),
                "jsonp": jsonp,
                "splits": "true",
                "stocks": "true",
            },
            quote_via=lambda s, *_args: quote(s, safe="/"),
        )
        return f"{self._BASE_URL}?{query}"

    def _request(self, url: str) -> list[list[float]]:
        request = Request(url, headers=self._HEADERS)
        with urlopen(request, timeout=self._request_timeout) as resp:
            body = cast(bytes, resp.read()).decode("utf-8")

        if "(" not in body or not body.rstrip().endswith(");"):
            raise FeedUnavailableError(
                f"Dukascopy feed returned an unexpected response: {body[:120]!r}"
            )

        open_paren = body.index("(")
        close_paren = body.rindex(");")
        payload = body[open_paren + 1 : close_paren]
        return cast(list[list[float]], json.loads(payload))

    def supported_symbols(self) -> list[Symbol]:
        return []
