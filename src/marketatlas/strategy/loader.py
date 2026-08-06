from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from marketatlas.analysis.analyzers.atr import ATRAnalyzer
from marketatlas.analysis.analyzers.atr_series import ATRSeriesAnalyzer
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.analyzers.sr import SupportResistanceAnalyzer
from marketatlas.analysis.analyzers.swing_basic import BasicSwingAnalyzer
from marketatlas.analysis.analyzers.swing_structure import SwingStructureAnalyzer
from marketatlas.analysis.analyzers.trend import TrendAnalyzer
from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.patterns import FourSwingPullbackDetector, PullbackPatternAnalyzer

from .config import AnalyzerConfig, RiskConfig, SignalConfig, StrategyConfig

ANALYZER_TYPES: dict[str, type[Analyzer]] = {
    "EMAAnalyzer": EMAAnalyzer,
    "ATRAnalyzer": ATRAnalyzer,
    "ATRSeriesAnalyzer": ATRSeriesAnalyzer,
    "TrendAnalyzer": TrendAnalyzer,
    "SwingStructureAnalyzer": SwingStructureAnalyzer,
    "BasicSwingAnalyzer": BasicSwingAnalyzer,
    "SupportResistanceAnalyzer": SupportResistanceAnalyzer,
    "FourSwingPullbackDetector": FourSwingPullbackDetector,
    "PullbackPatternAnalyzer": PullbackPatternAnalyzer,
}


class ConfigError(Exception):
    pass


def load_strategy(path: Path) -> StrategyConfig:
    if path.suffix == ".dsl":
        return _load_dsl(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ConfigError(f"Expected YAML mapping, got {type(raw).__name__}")

    strategy_block = raw.get("strategy")
    if not isinstance(strategy_block, dict):
        raise ConfigError("Missing 'strategy' block")

    name = strategy_block.get("name")
    version = strategy_block.get("version", "1.0")
    if not name:
        raise ConfigError("Missing 'strategy.name'")

    timeframes = _parse_timeframes(strategy_block.get("timeframes"))
    analyzers = _parse_analyzers(raw.get("analyzers", []))
    signals = _parse_signals(raw.get("signals", []))
    risk = _parse_risk(raw.get("risk"))

    return StrategyConfig(
        name=name,
        version=str(version),
        timeframes=timeframes,
        analyzers=analyzers,
        signals=signals,
        risk=risk,
    )


def _load_dsl(path: Path) -> StrategyConfig:
    from marketatlas.analysis.ast.compiler import ASTCompiler
    from marketatlas.analysis.ast.parser import parse_with_positions

    source = path.read_text()
    analysis, _ = parse_with_positions(source, name=path.stem)
    try:
        template = ASTCompiler.compile_template(analysis)
    except Exception as e:
        raise ConfigError(f"Error compiling DSL '{path.name}': {e}") from e
    return template.config


def validate_config(config: StrategyConfig) -> list[str]:
    errors: list[str] = []
    for i, ac in enumerate(config.analyzers):
        if ac.type not in ANALYZER_TYPES:
            errors.append(f"Unknown analyzer type '{ac.type}' at index {i}")

    # Build analyzers to check what they produce
    base_tf = config.timeframes[0] if config.timeframes else "1d"
    analyzers: list[Analyzer] = []
    for ac in config.analyzers:
        cls = ANALYZER_TYPES.get(ac.type)
        if cls is not None:
            kwargs = dict(ac.params)
            kwargs["timeframe"] = ac.timeframe if ac.timeframe is not None else base_tf
            analyzers.append(cls(**kwargs))

    produces_keys: set[FactKey] = set()
    for a in analyzers:
        for fk in a.produces():
            produces_keys.add(fk)

    for i, sc in enumerate(config.signals):
        for req_key in sc.requires:
            needed = FactKey(req_key)
            if needed not in produces_keys:
                errors.append(
                    f"Signal '{sc.type}' at index {i} requires '{req_key}' not found in analyzers"
                )
    return errors


def _parse_timeframes(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ("1d",)
    if isinstance(raw, list):
        return tuple(str(tf) for tf in raw)
    raise ConfigError("'strategy.timeframes' must be a list")


def _parse_analyzers(raw: Any) -> tuple[AnalyzerConfig, ...]:
    if not isinstance(raw, list):
        return ()
    configs: list[AnalyzerConfig] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"Analyzer at index {i} must be a mapping")
        atype = item.get("type")
        if not atype:
            raise ConfigError(f"Analyzer at index {i} missing 'type'")
        params = item.get("params", {})
        if not isinstance(params, dict):
            raise ConfigError(f"Analyzer at index {i} 'params' must be a mapping")
        tf = item.get("timeframe")
        if tf is not None and not isinstance(tf, str):
            raise ConfigError(f"Analyzer at index {i} 'timeframe' must be a string")
        configs.append(AnalyzerConfig(type=atype, params=params, timeframe=tf))
    return tuple(configs)


def _parse_signals(raw: Any) -> tuple[SignalConfig, ...]:
    if not isinstance(raw, list):
        return ()
    configs: list[SignalConfig] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"Signal at index {i} must be a mapping")
        stype = item.get("type")
        if not stype:
            raise ConfigError(f"Signal at index {i} missing 'type'")
        requires_raw = item.get("requires", [])
        if not isinstance(requires_raw, list):
            raise ConfigError(f"Signal at index {i} 'requires' must be a list")
        rules = item.get("rules", {})
        if not isinstance(rules, dict):
            raise ConfigError(f"Signal at index {i} 'rules' must be a mapping")
        configs.append(SignalConfig(type=stype, requires=tuple(requires_raw), rules=rules))
    return tuple(configs)


def _parse_risk(raw: Any) -> RiskConfig:
    if raw is None:
        return RiskConfig(algorithm="none")
    if not isinstance(raw, dict):
        raise ConfigError("'risk' must be a mapping")
    algorithm = raw.get("algorithm")
    if not algorithm:
        raise ConfigError("'risk' missing 'algorithm'")
    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise ConfigError("'risk.params' must be a mapping")
    return RiskConfig(algorithm=algorithm, params=params)


def build_analyzers(config: StrategyConfig) -> list[Analyzer]:
    base_tf = config.timeframes[0] if config.timeframes else "1d"
    analyzers: list[Analyzer] = []
    for ac in config.analyzers:
        cls = ANALYZER_TYPES.get(ac.type)
        if cls is None:
            raise ConfigError(f"Unknown analyzer type '{ac.type}'")
        kwargs = dict(ac.params)
        kwargs["timeframe"] = ac.timeframe if ac.timeframe is not None else base_tf
        analyzers.append(cls(**kwargs))
    return analyzers
