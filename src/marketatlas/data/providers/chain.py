from __future__ import annotations

from datetime import datetime

from marketatlas.data.providers.base import (
    DataProvider,
    NoDataAvailableError,
    RateLimitError,
    SymbolNotFoundError,
)
from marketatlas.data.types import MarketData, Symbol, Timeframe


class ProviderChain(DataProvider):
    def __init__(self, providers: list[DataProvider]) -> None:
        self._providers = providers

    @property
    def providers(self) -> list[DataProvider]:
        return list(self._providers)

    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData:
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                return provider.fetch(symbol, timeframe, start, end)
            except (SymbolNotFoundError, RateLimitError) as e:
                last_error = e
                continue

        raise NoDataAvailableError(symbol, timeframe) from last_error

    def supported_symbols(self) -> list[Symbol]:
        all_symbols: set[str] = set()
        for provider in self._providers:
            for symbol in provider.supported_symbols():
                all_symbols.add(symbol.name)
        return sorted((Symbol(name=s) for s in all_symbols), key=lambda s: s.name)
