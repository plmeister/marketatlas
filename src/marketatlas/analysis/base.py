from abc import ABC, abstractmethod
from collections.abc import Mapping

from marketatlas.data.types import Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact

from .factkey import FactKey
from .result import AnalysisResult


class Analyzer(ABC):
    def __init__(
        self,
        timeframe: Timeframe | str | None = None,
        bindings: Mapping[str, str] | None = None,
        name: str | None = None,
        fact_name: str | None = None,
    ):
        if isinstance(timeframe, str):
            timeframe = Timeframe(timeframe)
        self._timeframe = timeframe
        self._bindings = dict(bindings) if bindings else {}
        self._name = name or fact_name

    @property
    def instance_key(self) -> str:
        """Fact name this analyzer produces.

        ``name`` overrides the derived default so a parameterized fact can be
        bound to a fixed-name consumer input — e.g. a 480-period EMA feeding a
        consumer that expects ``ema_20`` — without renaming the consumer.

        ``fact_name`` is the DSL-reachable spelling of the same thing. Inside a
        definition block ``name`` is already the DSL's *reference* keyword, so
        ``ema { period: 480, name: ema_20 }`` asks for a definition named
        ``ema_20`` rather than renaming the produced fact; ``fact_name`` is
        unambiguous:
        ``ema20 := ema { period: 480, fact_name: ema_20 }``.
        """
        return self._name or type(self).__name__

    @property
    def timeframe(self) -> Timeframe | None:
        return self._timeframe

    def _make_key(self, key_str: str) -> FactKey:
        """Build a ``FactKey`` for a consumed fact name (backlog 062).

        A binding override (``{fact_name: key_string}``, injected by the AST
        compiler) replaces the fact name with a key string that may carry an
        explicit ``name@timeframe`` — the mechanism for cross-timeframe
        references. A binding never overrides the analyzer's own produced key
        (``instance_key``), so ``produces()`` stays stable. Without a binding
        the plain name resolves at the analyzer's own timeframe.
        """
        bound = self._bindings.get(key_str)
        if bound is not None and key_str != self.instance_key:
            key_str = bound
        if "@" in key_str:
            name, tf = key_str.rsplit("@", 1)
            return FactKey(name, timeframe=Timeframe(tf))
        return FactKey(key_str, timeframe=self._timeframe)

    @abstractmethod
    def requires(self) -> tuple[FactKey, ...]: ...

    @abstractmethod
    def produces(self) -> tuple[FactKey, ...]: ...

    @abstractmethod
    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult: ...
