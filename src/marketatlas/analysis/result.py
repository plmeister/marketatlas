from dataclasses import dataclass

from marketatlas.facts.base import Fact


@dataclass(frozen=True)
class AnalysisResult:
    facts: tuple[Fact, ...]
    evidence: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()
