from __future__ import annotations

import struct
import zlib
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from marketatlas.data.instrument import Instrument, InstrumentRegistry
from marketatlas.data.providers.base import NoDataAvailableError, RateLimitError
from marketatlas.data.providers.dukascopy import DukascopyProvider
from marketatlas.data.types import MarketData, Symbol, Timeframe

RECORD_FORMAT = struct.Struct(">Ifffff")


def _make_bi5(candles: list[tuple[int, float, float, float, float, float]]) -> bytes:
    """Pack (sec_offset, open, high, low, close, volume) tuples into BI5 binary."""
    data = bytearray()
    for c in candles:
        data.extend(RECORD_FORMAT.pack(c[0], c[1], c[2], c[3], c[4], c[5]))
    return zlib.compress(bytes(data))


class TestDukascopyProvider:
    def test_fetch_returns_market_data(self) -> None:
        bi5 = _make_bi5([
            (0, 100.0, 105.0, 99.0, 103.0, 1000.0),
            (3600, 103.0, 108.0, 102.0, 107.0, 1500.0),
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = bi5
            mock_urlopen.return_value = mock_resp

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
        bi5 = _make_bi5([
            (0, 100.0, 105.0, 99.0, 103.0, 1000.0),
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = bi5
            mock_urlopen.return_value = mock_resp

            provider = DukascopyProvider()
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

        assert result.candles[0].timestamp.tzinfo is not None
        assert result.candles[0].timestamp == datetime(2024, 1, 15, tzinfo=UTC)

    def test_fetch_unsupported_timeframe(self) -> None:
        provider = DukascopyProvider()
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            provider.fetch(
                Symbol("EURUSD"),
                Timeframe.W1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 8, tzinfo=UTC),
            )

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

        bi5 = _make_bi5([
            (0, 100.0, 105.0, 99.0, 103.0, 1000.0),
        ])

        fail = HTTPError("http://example.com", 429, "Too Many", Message(), None)

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = bi5
            mock_urlopen.side_effect = [fail, mock_resp]

            provider = DukascopyProvider(max_retries=3, retry_delay=0.01)
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 1
            assert mock_urlopen.call_count == 2

    def test_cache_avoids_network(self) -> None:
        bi5 = _make_bi5([
            (0, 100.0, 105.0, 99.0, 103.0, 1000.0),
        ])

        cache_dir = Path("/tmp/test_dukascopy_cache")
        cache_file = (
            cache_dir
            / "dukascopy"
            / "EURUSD"
            / "1h"
            / "2024"
            / "01"
            / "15.bi5"
        )

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(bi5)

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

    def test_fetch_multiple_days(self) -> None:
        bi5_day1 = _make_bi5([
            (0, 100.0, 105.0, 99.0, 103.0, 1000.0),
        ])
        bi5_day2 = _make_bi5([
            (0, 104.0, 108.0, 102.0, 106.0, 1200.0),
        ])

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            resp1 = MagicMock()
            resp1.__enter__.return_value = resp1
            resp1.read.return_value = bi5_day1
            resp2 = MagicMock()
            resp2.__enter__.return_value = resp2
            resp2.read.return_value = bi5_day2
            mock_urlopen.side_effect = [resp1, resp2]

            provider = DukascopyProvider()
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 16, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 2
            assert result.candles[0].open == 100.0
            assert result.candles[1].open == 104.0
            assert mock_urlopen.call_count == 2

    def test_fetch_no_data_raises(self) -> None:
        from urllib.error import HTTPError

        with patch("marketatlas.data.providers.dukascopy.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                "http://example.com", 404, "Not Found", Message(), None
            )

            provider = DukascopyProvider()
            with pytest.raises(NoDataAvailableError):
                provider.fetch(
                    Symbol("MISSING"),
                    Timeframe.H1,
                    datetime(2024, 1, 15, tzinfo=UTC),
                    datetime(2024, 1, 16, 23, 59, tzinfo=UTC),
                )

    def test_symbol_resolution_with_registry(self) -> None:
        bi5 = _make_bi5([
            (0, 100.0, 105.0, 99.0, 103.0, 1000.0),
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
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = bi5
            mock_urlopen.return_value = mock_resp

            provider = DukascopyProvider(registry=registry)
            result = provider.fetch(
                Symbol("EURUSD"),
                Timeframe.H1,
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 15, 23, 59, tzinfo=UTC),
            )

            assert len(result.candles) == 1
            called_url = mock_urlopen.call_args[0][0]
            assert "EUR/USD" in called_url

    def test_unsupported_timeframe_raises(self) -> None:
        provider = DukascopyProvider()

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            provider.fetch(
                Symbol("EURUSD"),
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 31, tzinfo=UTC),
            )

    def test_supported_symbols_returns_empty(self) -> None:
        provider = DukascopyProvider()
        assert provider.supported_symbols() == []
