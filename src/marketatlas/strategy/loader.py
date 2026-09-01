from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey

from .config import AnalyzerConfig, RiskConfig, SignalConfig, StrategyConfig

if TYPE_CHECKING:
    from marketatlas.analysis.ast.registry import ProviderRegistry


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


def validate_config(
    config: StrategyConfig,
    registry: ProviderRegistry | None = None,
) -> list[str]:
    classes = _analyzer_classes(registry)
    errors: list[str] = []
    for i, ac in enumerate(config.analyzers):
        if ac.type not in classes:
            errors.append(f"Unknown analyzer type '{ac.type}' at index {i}")

    # Build analyzers to check what they produce
    base_tf = config.timeframes[0] if config.timeframes else "1d"
    analyzers: list[Analyzer] = []
    for ac in config.analyzers:
        cls = classes.get(ac.type)
        if cls is not None:
            kwargs = dict(ac.params)
            kwargs["timeframe"] = ac.timeframe if ac.timeframe is not None else base_tf
            analyzers.append(cls(**kwargs))

    produces_keys: set[FactKey] = set()
    for a in analyzers:
        for fk in a.produces():
            produces_keys.add(fk)
    produced_names = {fk.name for fk in produces_keys}

    for i, sc in enumerate(config.signals):
        for req_key in sc.requires:
            name = req_key.split("@")[0]
            if name not in produced_names:
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


def build_analyzers(
    config: StrategyConfig,
    registry: ProviderRegistry | None = None,
) -> list[Analyzer]:
    classes = _analyzer_classes(registry)
    base_tf = config.timeframes[0] if config.timeframes else "1d"
    analyzers: list[Analyzer] = []
    for ac in config.analyzers:
        cls = classes.get(ac.type)
        if cls is None:
            raise ConfigError(f"Unknown analyzer type '{ac.type}'")
        kwargs = dict(ac.params)
        kwargs["timeframe"] = ac.timeframe if ac.timeframe is not None else base_tf
        analyzers.append(cls(**kwargs))
    return analyzers


def _analyzer_classes(registry: ProviderRegistry | None) -> dict[str, type[Analyzer]]:
    """Impl-name → analyzer class, from the (default) provider registry.

    The registry is the single source of truth for analyzer type resolution;
    ``ProviderRegistry.analyzer_classes()`` replaces the retired, separately
    maintained ``ANALYZER_TYPES`` map.
    """
    from marketatlas.analysis.ast.registry import create_default_registry

    reg = registry if registry is not None else create_default_registry()
    return reg.analyzer_classes()
