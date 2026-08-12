from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from marketatlas.data.datastore import DataStore
from marketatlas.data.instrument import Instrument, InstrumentRegistry
from marketatlas.data.providers.base import DataProvider
from marketatlas.data.resample import CannotResampleError, resample, tf_minutes
from marketatlas.data.types import MarketData, Symbol, Timeframe


class PortfolioError(ValueError):
    """Raised when a portfolio file is missing, malformed, or unresolvable."""


class InstrumentDataError(ValueError):
    """Raised when the required data for one instrument cannot be acquired."""

    def __init__(self, instrument: str, message: str) -> None:
        self.instrument = instrument
        super().__init__(f"{instrument}: {message}")


@dataclass(frozen=True)
class InstrumentData:
    """Multi-timeframe data acquired for a single portfolio instrument."""

    instrument: Instrument
    timeframes: dict[Timeframe, MarketData]
    resampled: tuple[tuple[Timeframe, Timeframe], ...]

    @property
    def symbol(self) -> Symbol:
        return Symbol(self.instrument.canonical)

    @property
    def base(self) -> MarketData:
        return self.timeframes[min(self.timeframes, key=tf_minutes)]


class PortfolioSpec:
    """Declared instrument list for a portfolio backtest (file order preserved)."""

    def __init__(self, instruments: tuple[Instrument, ...]) -> None:
        self._instruments = instruments

    @property
    def instruments(self) -> tuple[Instrument, ...]:
        return self._instruments

    def __len__(self) -> int:
        return len(self._instruments)

    def __iter__(self) -> Any:
        return iter(self._instruments)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PortfolioSpec):
            return NotImplemented
        return self._instruments == other._instruments


def load_portfolio(path: Path, registry: InstrumentRegistry) -> PortfolioSpec:
    """Parse a portfolio file and resolve every canonical against the registry.

    File format::

        instruments:
          - GBPUSD
          - BTCUSD

    Canonical names only; provider symbols are a registry concern (068).
    Duplicate canonicals are deduped while keeping file order. Raises
    :class:`PortfolioError` on a missing/malformed/empty file, an unresolved
    canonical (naming the instrument and its index), or a missing registry.
    """
    if registry is None:
        raise PortfolioError("no instrument registry available (data/instruments.yaml)")
    if not path.exists():
        raise PortfolioError(f"portfolio file not found: {path}")
    raw = path.read_text()
    if not raw.strip():
        raise PortfolioError(f"portfolio file is empty: {path}")
    data: Any = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise PortfolioError(f"portfolio file must be a mapping with an 'instruments' key: {path}")
    if "instruments" not in data:
        raise PortfolioError(f"portfolio file missing 'instruments' key: {path}")
    names = data["instruments"]
    if names is None:
        names = []
    if not isinstance(names, list):
        raise PortfolioError(f"'instruments' must be a list of canonical names: {path}")
    if not names:
        raise PortfolioError(f"portfolio file declares no instruments: {path}")

    seen: set[str] = set()
    instruments: list[Instrument] = []
    for i, name in enumerate(names):
        if not isinstance(name, str):
            raise PortfolioError(
                f"portfolio entry at index {i} must be a canonical name "
                f"string, got {type(name).__name__}"
            )
        inst = registry.get(name)
        if inst is None:
            raise PortfolioError(f"Unknown instrument '{name}' at index {i} in portfolio file")
        if name in seen:
            continue
        seen.add(name)
        instruments.append(inst)
    return PortfolioSpec(tuple(instruments))


def _find_resample_source(
    target: Timeframe,
    fetched: dict[Timeframe, MarketData],
) -> Timeframe | None:
    target_mins = tf_minutes(target)
    candidates = [(tf, tf_minutes(tf)) for tf in fetched if tf_minutes(tf) < target_mins]
    if not candidates:
        return None
    return min(candidates, key=lambda x: x[1])[0]


def fetch_instrument_data(
    provider: DataProvider,
    datastore: DataStore,
    instrument: Instrument,
    timeframes: Sequence[Timeframe],
    start: datetime,
    end: datetime,
    base_tf: Timeframe,
    label: str = "",
) -> InstrumentData:
    """Acquire all required timeframes for one instrument over a fixed range.

    Serves covered ranges from the persistent store first, then tries a
    native fetch per timeframe, then resamples from the nearest higher
    resolution already fetched. Progress lines are printed with an optional
    ``label`` prefix (the canonical name in portfolio runs).

    Raises :class:`InstrumentDataError` naming the instrument when the
    primary ``base_tf`` cannot be acquired, so a portfolio run can abort
    that instrument instead of silently running partial data.
    """
    symbol = Symbol(instrument.canonical)
    prefix = f"  {label} " if label else "  "
    fetched: dict[Timeframe, MarketData] = {}
    resampled: list[tuple[Timeframe, Timeframe]] = []

    for tf in timeframes:
        # Serve from the persistent store when the range is already covered.
        if datastore.has(symbol, tf, start, end):
            md = datastore.get(symbol, tf, start, end)
            if md is not None and md.candles:
                fetched[tf] = md
                print(f"{prefix}{tf.value}: served from store ({len(md.candles)} candles)")
                continue

        # Try native fetch first
        try:
            md = provider.fetch(symbol, tf, start, end)
            datastore.put(md)
            fetched[tf] = md
            print(f"{prefix}{tf.value}: fetched natively ({len(md.candles)} candles)")
            continue
        except ValueError:
            pass
        except Exception as e:
            print(f"{prefix}{tf.value}: fetch error — {e}", file=sys.stderr)
            continue

        # Native not supported — try resample from nearest higher-res
        source_tf = _find_resample_source(tf, fetched)
        if source_tf is None:
            print(f"{prefix}{tf.value}: cannot fetch or resample (no source data)")
            continue

        try:
            candles = resample(fetched[source_tf].candles, source_tf, tf)
            md = MarketData(symbol=symbol, timeframe=tf, candles=candles)
            datastore.put(md)
            fetched[tf] = md
            resampled.append((tf, source_tf))
            print(f"{prefix}{tf.value}: resampled from {source_tf.value} ({len(candles)} candles)")
        except CannotResampleError as e:
            print(f"{prefix}{tf.value}: cannot resample — {e}")

    if base_tf not in fetched:
        raise InstrumentDataError(
            instrument.canonical,
            f"primary timeframe {base_tf.value} not available",
        )
    return InstrumentData(
        instrument=instrument,
        timeframes=fetched,
        resampled=tuple(resampled),
    )
