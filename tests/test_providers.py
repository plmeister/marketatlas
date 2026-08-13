from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from marketatlas.data.providers.base import (
    DataProvider,
    FeedUnavailableError,
    NoDataAvailableError,
    RateLimitError,
    SymbolNotFoundError,
    UnsupportedTimeframeError,
)
from marketatlas.data.providers.chain import ProviderChain
from marketatlas.data.providers.yahoo import YahooProvider
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


class MockProvider(DataProvider):
    def __init__(self, candles: list[Candle] | None = None, error: Exception | None = None) -> None:
        self._candles = candles or []
        self._error = error
        self.call_count = 0

    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData:
        self.call_count += 1
        if self._error:
            raise self._error
        return MarketData(symbol=symbol, timeframe=timeframe, candles=tuple(self._candles))

    def supported_symbols(self) -> list[Symbol]:
        return []


class TestProviderChain:
    def test_chain_uses_first_provider(self) -> None:
        candles = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                open=100.0,
                high=105.0,
                low=99.0,
                close=103.0,
                volume=1000.0,
            )
        ]
        provider1 = MockProvider(candles=candles)
        provider2 = MockProvider()

        chain = ProviderChain([provider1, provider2])
        result = chain.fetch(
            Symbol("BTC"), Timeframe.H1, datetime(2024, 1, 1), datetime(2024, 1, 2)
        )

        assert result.candles == tuple(candles)
        assert provider1.call_count == 1
        assert provider2.call_count == 0

    def test_chain_falls_back_on_error(self) -> None:
        candles = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                open=100.0,
                high=105.0,
                low=99.0,
                close=103.0,
                volume=1000.0,
            )
        ]
        provider1 = MockProvider(error=SymbolNotFoundError(Symbol("BTC")))
        provider2 = MockProvider(candles=candles)

        chain = ProviderChain([provider1, provider2])
        result = chain.fetch(
            Symbol("BTC"), Timeframe.H1, datetime(2024, 1, 1), datetime(2024, 1, 2)
        )

        assert result.candles == tuple(candles)
        assert provider1.call_count == 1
        assert provider2.call_count == 1

    def test_chain_raises_when_all_fail(self) -> None:
        provider1 = MockProvider(error=SymbolNotFoundError(Symbol("BTC")))
        provider2 = MockProvider(error=RateLimitError())

        chain = ProviderChain([provider1, provider2])

        with pytest.raises(NoDataAvailableError):
            chain.fetch(Symbol("BTC"), Timeframe.H1, datetime(2024, 1, 1), datetime(2024, 1, 2))

    def test_chain_falls_back_on_unsupported_timeframe(self) -> None:
        """A provider rejecting the timeframe must not stop the chain (073)."""
        candles = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                open=100.0,
                high=105.0,
                low=99.0,
                close=103.0,
                volume=1000.0,
            )
        ]
        provider1 = MockProvider(error=UnsupportedTimeframeError(Symbol("EURUSD"), Timeframe.D1))
        provider2 = MockProvider(candles=candles)

        chain = ProviderChain([provider1, provider2])
        result = chain.fetch(
            Symbol("EURUSD"), Timeframe.D1, datetime(2024, 1, 1), datetime(2024, 1, 2)
        )

        assert result.candles == tuple(candles)
        assert provider1.call_count == 1
        assert provider2.call_count == 1

    def test_chain_falls_back_on_feed_unavailable(self) -> None:
        candles = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                open=100.0,
                high=105.0,
                low=99.0,
                close=103.0,
                volume=1000.0,
            )
        ]
        provider1 = MockProvider(error=FeedUnavailableError("dukascopy down"))
        provider2 = MockProvider(candles=candles)

        chain = ProviderChain([provider1, provider2])
        result = chain.fetch(
            Symbol("EURUSD"), Timeframe.H1, datetime(2024, 1, 1), datetime(2024, 1, 2)
        )

        assert result.candles == tuple(candles)
        assert provider1.call_count == 1
        assert provider2.call_count == 1

    def test_chain_all_unavailable_raises_no_data(self) -> None:
        provider1 = MockProvider(error=FeedUnavailableError("dukascopy down"))
        provider2 = MockProvider(error=FeedUnavailableError("yahoo down"))

        chain = ProviderChain([provider1, provider2])

        with pytest.raises(NoDataAvailableError):
            chain.fetch(
                Symbol("EURUSD"), Timeframe.H1, datetime(2024, 1, 1), datetime(2024, 1, 2)
            )

    def test_chain_all_unsupported_re_raises_unsupported(self) -> None:
        """Every provider rejecting the TF keeps the unsupported signal."""
        provider1 = MockProvider(error=UnsupportedTimeframeError(Symbol("EURUSD"), Timeframe.D1))
        provider2 = MockProvider(error=UnsupportedTimeframeError(Symbol("EURUSD"), Timeframe.D1))

        chain = ProviderChain([provider1, provider2])

        with pytest.raises(UnsupportedTimeframeError, match="Unsupported timeframe"):
            chain.fetch(
                Symbol("EURUSD"), Timeframe.D1, datetime(2024, 1, 1), datetime(2024, 1, 2)
            )

    def test_chain_hard_error_stops_chain(self) -> None:
        """Hard failures (network) propagate instead of silently degrading."""
        provider1 = MockProvider(error=RuntimeError("connection refused"))
        provider2 = MockProvider()

        chain = ProviderChain([provider1, provider2])

        with pytest.raises(RuntimeError, match="connection refused"):
            chain.fetch(Symbol("BTC"), Timeframe.H1, datetime(2024, 1, 1), datetime(2024, 1, 2))
        assert provider2.call_count == 0

    def test_chain_supported_symbols(self) -> None:
        provider1 = MockProvider()
        provider1.supported_symbols = MagicMock(return_value=[Symbol("BTC"), Symbol("ETH")])
        provider2 = MockProvider()
        provider2.supported_symbols = MagicMock(return_value=[Symbol("ETH"), Symbol("SOL")])

        chain = ProviderChain([provider1, provider2])
        symbols = chain.supported_symbols()

        assert symbols == [Symbol("BTC"), Symbol("ETH"), Symbol("SOL")]


class TestYahooProvider:
    @patch("yfinance.Ticker")
    def test_fetch_returns_market_data(self, mock_ticker: MagicMock) -> None:
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__iter__ = MagicMock(
            return_value=iter(
                [
                    (
                        datetime(2024, 1, 1),
                        MagicMock(
                            Open=100.0,
                            High=105.0,
                            Low=99.0,
                            Close=103.0,
                            Volume=1000.0,
                        ),
                    )
                ]
            )
        )
        mock_ticker.return_value.history.return_value = mock_df

        provider = YahooProvider()
        result = provider.fetch(
            Symbol("BTC"),
            Timeframe.H1,
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
        )

        assert isinstance(result, MarketData)
        assert result.symbol == Symbol("BTC")
        assert result.timeframe == Timeframe.H1

    @patch("yfinance.Ticker")
    def test_fetch_empty_raises(self, mock_ticker: MagicMock) -> None:
        mock_df = MagicMock()
        mock_df.empty = True
        mock_ticker.return_value.history.return_value = mock_df

        provider = YahooProvider()

        with pytest.raises(SymbolNotFoundError):
            provider.fetch(
                Symbol("MISSING"),
                Timeframe.H1,
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
            )

    def test_fetch_unsupported_timeframe(self) -> None:
        provider = YahooProvider()
        provider._TIMEFRAME_MAP = {}  # Clear map to test unsupported timeframe

        with pytest.raises(UnsupportedTimeframeError, match="Unsupported timeframe"):
            provider.fetch(
                Symbol("BTC"),
                Timeframe.H1,
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
            )
