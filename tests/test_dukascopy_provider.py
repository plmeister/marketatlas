from __future__ import annotations

import json
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from marketatlas.data.instrument import Instrument, InstrumentRegistry
from marketatlas.data.providers.base import (
    FeedUnavailableError,
    NoDataAvailableError,
    RateLimitError,
)
from marketatlas.data.providers.dukascopy import DukascopyProvider
from marketatlas.data.types import MarketData, Symbol, Timeframe


def _make_jsonp(rows: list[list[float]]) -> bytes:
    """Wrap [ms, open, high, low, close, volume] rows in a JSONP response."""
    return f"probe_cb({json.dumps(rows)});".encode()


def _mock_response(body: bytes) -> MagicMock:
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = body
    return resp


class TestDukascopyProvider:
    def test_fetch_returns_market_data(self) -> None:
        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
            [1705280400000, 103.0, 108.0, 102.0, 107.0, 1500.0],
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _mock_response(body)

            provider = DukascopyProvider()
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

        assert isinstance(result, MarketData)
        assert result.symbol == Symbol("EURUSD")
        assert result.timeframe == Timeframe.H1
        assert len(result.candles) == 2

        c0 = result.candles[0]
        assert c0.open == 100.0
        assert c0.high == 105.0
        assert c0.low == 99.0
        assert c0.close == 103.0
        assert c0.volume == 1000.0

        c1 = result.candles[1]
        assert c1.open == 103.0
        assert c1.high == 108.0
        assert c1.low == 102.0
        assert c1.close == 107.0
        assert c1.volume == 1500.0

    def test_fetch_timestamps_are_utc(self) -> None:
        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _mock_response(body)

            provider = DukascopyProvider()
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

        assert result.candles[0].timestamp.tzinfo is not None
        assert result.candles[0].timestamp == datetime(2024, 1, 15, tzinfo=UTC)

    def test_all_timeframes_supported(self) -> None:
        provider = DukascopyProvider()
        for tf in Timeframe:
            assert provider._interval(Symbol("EURUSD"), tf)

    def test_fetch_daily(self) -> None:
        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
            [1705363200000, 104.0, 108.0, 102.0, 106.0, 1200.0],
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _mock_response(body)

            provider = DukascopyProvider()
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.D1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 16, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 2
            assert result.candles[0].timestamp == datetime(2024, 1, 15, tzinfo=UTC)
            assert result.candles[1].timestamp == datetime(2024, 1, 16, tzinfo=UTC)
            url = mock_urlopen.call_args[0][0].get_full_url()
            assert "interval=1DAY" in url
            assert "instrument=EUR/USD" in url
            assert "offer_side=B" in url
            assert "path=chart/json3" in url

    def test_fetch_weekly(self) -> None:
        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _mock_response(body)

            provider = DukascopyProvider()
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.W1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 21, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 1
            url = mock_urlopen.call_args[0][0].get_full_url()
            assert "interval=1WEEK" in url

    def test_pagination_advances_cursor(self) -> None:
        # Two pages; page two repeats the boundary row which must be dropped.
        page1 = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
            [1705280400000, 103.0, 108.0, 102.0, 107.0, 1500.0],
        ])
        page2 = _make_jsonp([
            [1705280400000, 103.0, 108.0, 102.0, 107.0, 1500.0],
            [1705284000000, 107.0, 110.0, 106.0, 109.0, 900.0],
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = [_mock_response(page1), _mock_response(page2)]

            provider = DukascopyProvider()
            provider._PAGE_LIMIT = 2
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 3
            assert mock_urlopen.call_count == 2
            second_url = mock_urlopen.call_args_list[1][0][0].get_full_url()
            assert f"last_update={1705280400000}" in second_url

    def test_pagination_stops_at_end(self) -> None:
        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
            [1705363200000, 104.0, 108.0, 102.0, 106.0, 1200.0],
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _mock_response(body)

            provider = DukascopyProvider()
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 1
            assert mock_urlopen.call_count == 1

    def test_fetch_404_raises_no_data(self) -> None:
        from urllib.error import HTTPError

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                "http://example.com", 404, "Not Found", Message(), None
            )

            provider = DukascopyProvider()
            with pytest.raises(NoDataAvailableError):
                provider.fetch(
                    Symbol("EURUSD"),
                    Timeframe.H1,
                    datetime(2024, 1, 15, tzinfo=UTC),
                    datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
                )

    def test_rate_limit_retries_then_raises(self) -> None:
        from urllib.error import HTTPError

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                "http://example.com", 429, "Too Many", Message(), None
            )

            provider = DukascopyProvider(max_retries=2, retry_delay=0.01)
            with pytest.raises(RateLimitError):
                provider.fetch(
                    Symbol("EURUSD"),
                    Timeframe.H1,
                    datetime(2024, 1, 15, tzinfo=UTC),
                    datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
                )

            assert mock_urlopen.call_count == 2

    def test_rate_limit_then_succeeds(self) -> None:
        from urllib.error import HTTPError

        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
        ])

        fail = HTTPError("http://example.com", 429, "Too Many", Message(), None)

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = [fail, _mock_response(body)]

            provider = DukascopyProvider(max_retries=3, retry_delay=0.01)
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 1
            assert mock_urlopen.call_count == 2

    def test_http_503_retries_then_feed_unavailable(self) -> None:
        from urllib.error import HTTPError

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                "http://example.com", 503, "Service Unavailable", Message(), None
            )

            provider = DukascopyProvider(max_retries=2, retry_delay=0.01)
            with pytest.raises(FeedUnavailableError):
                provider.fetch(
                    Symbol("EURUSD"),
                    Timeframe.H1,
                    datetime(2024, 1, 15, tzinfo=UTC),
                    datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
                )

            assert mock_urlopen.call_count == 2

    def test_http_503_then_succeeds(self) -> None:
        from urllib.error import HTTPError

        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
        ])

        fail = HTTPError("http://example.com", 503, "Service Unavailable", Message(), None)

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = [fail, _mock_response(body)]

            provider = DukascopyProvider(max_retries=3, retry_delay=0.01)
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 1
            assert mock_urlopen.call_count == 2

    def test_urlerror_retries_then_feed_unavailable(self) -> None:
        from urllib.error import URLError

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("connection reset")

            provider = DukascopyProvider(max_retries=2, retry_delay=0.01)
            with pytest.raises(FeedUnavailableError) as excinfo:
                provider.fetch(
                    Symbol("EURUSD"),
                    Timeframe.H1,
                    datetime(2024, 1, 15, tzinfo=UTC),
                    datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
                )

            assert "EUR/USD" in str(excinfo.value)
            assert mock_urlopen.call_count == 2

    def test_urlerror_then_succeeds(self) -> None:
        from urllib.error import URLError

        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = [URLError("reset"), _mock_response(body)]

            provider = DukascopyProvider(max_retries=3, retry_delay=0.01)
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 1

    def test_cache_avoids_network(self) -> None:
        rows = [[1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0]]
        cache_dir = Path("/tmp/test_dukascopy_cache")
        cache_file = cache_dir / "dukascopy" / "EUR/USD" / "1h" / "1705276800000.json"

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(rows), encoding="utf-8")

        try:
            with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
                provider = DukascopyProvider(cache_dir=cache_dir)
                result = provider.fetch(
                    Symbol("EURUSD"),
                    Timeframe.H1,
                    datetime(2024, 1, 15, tzinfo=UTC),
                    datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
                )

            assert len(result.candles) == 1
            mock_urlopen.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(str(cache_dir))

    def test_fetch_no_data_raises(self) -> None:
        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _mock_response(_make_jsonp([]))

            provider = DukascopyProvider()
            with pytest.raises(NoDataAvailableError):
                provider.fetch(
                    Symbol("MISSING"),
                    Timeframe.H1,
                    datetime(2024, 1, 15, tzinfo=UTC),
                    datetime(2024, 1, 16, 23, 59, tzinfo=UTC),
                )

    def test_symbol_resolution_with_registry(self) -> None:
        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
        ])

        registry = InstrumentRegistry()
        registry.add(
            Instrument(
                canonical="EURUSD",
                asset_class="forex",
                description="Euro/US Dollar",
                providers={"dukascopy": "EUR/USD"},
            )
        )

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _mock_response(body)

            provider = DukascopyProvider(registry=registry)
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 1
            called_url = mock_urlopen.call_args[0][0].get_full_url()
            assert "EUR/USD" in called_url

    def test_symbol_resolution_default_slash_format(self) -> None:
        body = _make_jsonp([
            [1705276800000, 100.0, 105.0, 99.0, 103.0, 1000.0],
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _mock_response(body)

            provider = DukascopyProvider()
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 1
            called_url = mock_urlopen.call_args[0][0].get_full_url()
            assert "instrument=EUR/USD" in called_url

    def test_symbol_resolution_passthrough_non_fx(self) -> None:
        assert DukascopyProvider()._resolve_symbol(Symbol("BTC/USD")) == "BTC/USD"
        assert DukascopyProvider()._resolve_symbol(Symbol("XAUUSD")) == "XAU/USD"

    def test_supported_symbols_returns_empty(self) -> None:
        provider = DukascopyProvider()
        assert provider.supported_symbols() == []
