from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from marketatlas.analysis.ast.expressions import Expression, LiteralExpression
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

    def required_timeframes(self) -> tuple[Timeframe, ...]:
        """Timeframes this analysis needs (backlog 065), declaration order.

        Thin wrapper over the ``timeframes`` field: converts the declared
        ``TimeFrame`` resolutions to ``Timeframe`` values, deduplicated.
        Empty when no ``TimeFrame`` definitions are declared — the effective
        base timeframe is a runtime/``StrategyConfig`` concern that surfaces
        on the compiled ``TemplateGraph``.
        """
        from marketatlas.analysis.ast.requirements import required_timeframes

        return required_timeframes(self)


def is_timeframe_definition(definition: Definition) -> bool:
    """Whether a definition produces a compile-time timeframe value.

    A ``TimeFrame`` definition (capability key ``timeframe``) is a value
    producer: its ``resolution`` parameter is resolved at compile time and
    injected into ``AnalyzerConfig.timeframe`` (backlog 061). The capability
    key doubles as the provider name, so the marker holds before and after
    registry resolution.
    """
    return definition.provider == "timeframe"


def derive_timeframes(definitions: Sequence[Definition]) -> tuple[str, ...]:
    """Declared timeframe set for an analysis (backlog 061).

    Collects the ``resolution`` of every ``TimeFrame`` definition in first-seen
    order, deduplicated. A ``resolution`` is a simple string literal
    (``"1w"``); a template ``ChoiceExpression`` is skipped — the resolved,
    in-use set is computed per concrete AST by the compiler's resolution pass.
    An analysis with no ``TimeFrame`` definitions yields ``()`` (the
    strategy-level default applies at compile time).
    """
    result: list[str] = []
    for d in definitions:
        if not is_timeframe_definition(d):
            continue
        for p in d.parameters:
            if p.name != "resolution":
                continue
            value = p.value.value if isinstance(p.value, LiteralExpression) else p.value
            tf = _coerce_timeframe(value)
            if tf is not None and tf.value not in result:
                result.append(tf.value)
    return tuple(result)


def _coerce_timeframe(value: object) -> Timeframe | None:
    if isinstance(value, Timeframe):
        return value
    if not isinstance(value, str):
        return None
    try:
        return Timeframe(value)
    except ValueError:
        return None
