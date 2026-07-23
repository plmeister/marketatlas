from abc import ABC, abstractmethod
from datetime import datetime

from marketatlas.data.types import MarketData, Symbol, Timeframe


class SymbolNotFoundError(Exception):
    def __init__(self, symbol: Symbol) -> None:
        self.symbol = symbol
        super().__init__(f"Symbol not found: {symbol.name}")


class RateLimitError(Exception):
    pass


class NoDataAvailableError(Exception):
    def __init__(self, symbol: Symbol, timeframe: Timeframe) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        super().__init__(f"No data available for {symbol.name} {timeframe.value}")


class DataProvider(ABC):
    @abstractmethod
    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData: ...

    @abstractmethod
    def supported_symbols(self) -> list[Symbol]: ...
