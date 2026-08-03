from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from marketatlas.analysis.ast.expressions import Expression
from marketatlas.data.types import Timeframe


class BaseNode:
    id: str
    metadata: dict[str, str] | None

    def __init__(self, id: str = "", metadata: dict[str, str] | None = None) -> None:
        self.id = id
        self.metadata = metadata


@dataclass(frozen=True)
class Parameter:
    name: str
    value: Expression


@dataclass(frozen=True)
class Binding:
    source: str
    output: str
    target: str
    input: str


@dataclass(frozen=True)
class Capability:
    id: str
    description: str
    required_params: tuple[str, ...] = ()


@dataclass(frozen=True)
class Provider:
    name: str
    capability: str
    category: str
    impl: str
    default_params: tuple[Parameter, ...] = ()


@dataclass(frozen=True)
class Definition:
    name: str
    provider: str
    parameters: tuple[Parameter, ...] = ()
    bindings: tuple[Binding, ...] = ()
    timeframe: Timeframe | None = None
    id: str = ""
    metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class Analysis:
    name: str
    version: str
    definitions: tuple[Definition, ...] = ()
    providers: tuple[Provider, ...] = ()
    timeframes: tuple[str, ...] = ()
    id: str = ""
    metadata: dict[str, str] | None = None


def derive_timeframes(
    base: Timeframe | None,
    definitions: Sequence[Definition],
) -> tuple[str, ...]:
    """Declared timeframe set for an analysis (backlog 061).

    The base timeframe (``timeframes[0]``) is ``base`` when given — otherwise
    the first definition carrying an explicit timeframe. Definition timeframes
    follow in first-seen order, deduplicated. An analysis with no base and no
    explicit definition timeframes yields ``()`` (the strategy-level default
    applies at compile time).
    """
    result: list[str] = []
    if base is not None:
        result.append(base.value)
    for d in definitions:
        if d.timeframe is not None and d.timeframe.value not in result:
            result.append(d.timeframe.value)
    return tuple(result)
