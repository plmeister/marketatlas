from abc import ABC, abstractmethod

from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact

from .result import AnalysisResult


class Analyzer(ABC):
    @abstractmethod
    def requires(self) -> tuple[type[Fact], ...]: ...

    @abstractmethod
    def produces(self) -> tuple[type[Fact], ...]: ...

    @abstractmethod
    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult: ...
