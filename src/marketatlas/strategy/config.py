from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AnalyzerConfig:
    type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalConfig:
    type: str
    requires: tuple[str, ...] = ()
    rules: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskConfig:
    algorithm: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    version: str
    analyzers: tuple[AnalyzerConfig, ...] = ()
    signals: tuple[SignalConfig, ...] = ()
    risk: RiskConfig = field(default_factory=lambda: RiskConfig(algorithm="none"))
