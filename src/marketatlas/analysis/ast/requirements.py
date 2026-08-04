from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from marketatlas.analysis.ast.models import Analysis
from marketatlas.data.instrument import Instrument
from marketatlas.data.types import MarketData, Symbol, Timeframe

if TYPE_CHECKING:
    from marketatlas.data.datastore import DataStore


def required_timeframes(analysis: Analysis) -> tuple[Timeframe, ...]:
    """Timeframes the analysis needs, before instruments are known (backlog 065).

    Derived from ``Analysis.timeframes`` (the declared ``TimeFrame`` definition
    resolutions, backlog 061): first-seen order, deduplicated. An analysis with
    no ``TimeFrame`` definitions yields ``()`` — the effective base timeframe
    is a runtime/``StrategyConfig`` concern and surfaces on the compiled
    ``TemplateGraph``, not here.
    """
    result: list[Timeframe] = []
    seen: set[Timeframe] = set()
    for value in analysis.timeframes:
        try:
            tf = Timeframe(value)
        except ValueError:
            continue
        if tf not in seen:
            seen.add(tf)
            result.append(tf)
    return tuple(result)


@dataclass(frozen=True)
class DataRequirement:
    """One ``(instrument, timeframe)`` data need with its coverage window.

    ``start``/``end`` carry the run's date range so the caller can check store
    coverage (backlog 066) before any fetch is attempted.
    """

    instrument: Instrument
    timeframe: Timeframe
    start: datetime
    end: datetime


def required_data(
    analysis: Analysis,
    instruments: Sequence[Instrument],
    start: datetime,
    end: datetime,
) -> tuple[DataRequirement, ...]:
    """The ``(instrument, timeframe)`` pairs a run of ``analysis`` needs.

    Cartesian product over the declared timeframes (backlog 061) and the
    runtime instrument list (backlog 063), deduplicated by instrument identity
    (first occurrence wins) and deterministic: instrument order is the input
    order, timeframes are declaration order. An empty instrument list raises —
    there is nothing to run against (matching backlog 063). An analysis with no
    timeframes yields ``()``.
    """
    if not instruments:
        raise ValueError("At least one instrument is required to derive data requirements")
    unique = _dedup_instruments(instruments)
    tfs = required_timeframes(analysis)
    return tuple(
        DataRequirement(instrument=instrument, timeframe=tf, start=start, end=end)
        for instrument in unique
        for tf in tfs
    )


class _Fetcher(Protocol):
    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData: ...


def ensure_required_data(
    store: DataStore,
    requirements: Sequence[DataRequirement],
    provider: _Fetcher,
    resolve_symbol: Callable[[Instrument], Symbol],
) -> tuple[MarketData, ...]:
    """Fetch/store data for every requirement, closing only coverage gaps.

    Integrates with the persistent store (backlog 066): ``DataStore.
    fetch_or_get`` serves already-covered ranges from cache and fetches only
    the uncovered gaps. ``resolve_symbol`` maps an ``Instrument`` to the
    provider's ``Symbol`` (e.g. via ``InstrumentRegistry.get_symbol``).
    """
    from marketatlas.data.datastore import DataStore

    assert isinstance(store, DataStore)
    result: list[MarketData] = []
    for req in requirements:
        symbol = resolve_symbol(req.instrument)
        md = store.fetch_or_get(provider, symbol, req.timeframe, req.start, req.end)
        result.append(md)
    return tuple(result)


def _config_timeframes(config: object) -> tuple[Timeframe, ...]:
    """Effective timeframes of a compiled ``StrategyConfig`` (backlog 065).

    Uses ``config.timeframes`` — the declared ``Analysis.timeframes`` or the
    strategy base default (``("1d",)``) when the template declared none — so
    the template always knows exactly what it will run against, including the
    default base timeframe a bare AST cannot express.
    """
    from marketatlas.strategy.config import StrategyConfig

    assert isinstance(config, StrategyConfig)
    result: list[Timeframe] = []
    seen: set[Timeframe] = set()
    for value in config.timeframes:
        try:
            tf = Timeframe(value)
        except ValueError:
            continue
        if tf not in seen:
            seen.add(tf)
            result.append(tf)
    return tuple(result)


def _requirements_for(
    config: object,
    instruments: Sequence[Instrument],
    start: datetime,
    end: datetime,
) -> tuple[DataRequirement, ...]:
    """Data requirements for a compiled config (backlog 065)."""
    if not instruments:
        raise ValueError("At least one instrument is required to derive data requirements")
    unique = _dedup_instruments(instruments)
    tfs = _config_timeframes(config)
    return tuple(
        DataRequirement(instrument=instrument, timeframe=tf, start=start, end=end)
        for instrument in unique
        for tf in tfs
    )


def _dedup_instruments(instruments: Sequence[Instrument]) -> list[Instrument]:
    seen: set[str] = set()
    unique: list[Instrument] = []
    for instrument in instruments:
        if instrument.canonical in seen:
            continue
        seen.add(instrument.canonical)
        unique.append(instrument)
    return unique
