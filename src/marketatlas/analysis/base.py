from abc import ABC, abstractmethod

from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact

from .factkey import FactKey
from .result import AnalysisResult


class Analyzer(ABC):
    @property
    def instance_key(self) -> str:
        return type(self).__name__

    @abstractmethod
    def requires(self) -> tuple[FactKey, ...]: ...

    @abstractmethod
    def produces(self) -> tuple[FactKey, ...]: ...

    @abstractmethod
    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult: ...
