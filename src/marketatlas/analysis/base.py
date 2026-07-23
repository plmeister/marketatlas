from abc import ABC, abstractmethod

from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact

from .result import AnalysisResult


class Analyzer(ABC):
    @property
    def instance_key(self) -> str:
        return type(self).__name__

    @abstractmethod
    def requires(self) -> tuple[tuple[type[Fact], str], ...]: ...

    @abstractmethod
    def produces(self) -> tuple[tuple[type[Fact], str], ...]: ...

    @abstractmethod
    def analyze(
        self, view: MarketView, facts: dict[tuple[type[Fact], str], Fact]
    ) -> AnalysisResult: ...
