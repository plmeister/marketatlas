from abc import ABC, abstractmethod

from marketatlas.data.types import Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact

from .factkey import FactKey
from .result import AnalysisResult


class Analyzer(ABC):
    def __init__(self, timeframe: Timeframe | str | None = None):
        if isinstance(timeframe, str):
            timeframe = Timeframe(timeframe)
        self._timeframe = timeframe

    @property
    def instance_key(self) -> str:
        return type(self).__name__

    @property
    def timeframe(self) -> Timeframe | None:
        return self._timeframe

    def _make_key(self, key_str: str) -> FactKey:
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
