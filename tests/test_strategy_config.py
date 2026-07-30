from pathlib import Path

import pytest

from marketatlas.analysis.analyzers.atr import ATRAnalyzer
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.analyzers.trend import TrendAnalyzer
from marketatlas.strategy.config import (
    AnalyzerConfig,
    RiskConfig,
    SignalConfig,
    StrategyConfig,
)
from marketatlas.strategy.loader import (
    ANALYZER_TYPES,
    ConfigError,
    build_analyzers,
    load_strategy,
    validate_config,
)

VALID_YAML = """\
strategy:
  name: test_strategy
  version: "2.0"

analyzers:
  - type: EMAAnalyzer
    params: { period: 20 }
  - type: EMAAnalyzer
    params: { period: 50 }
  - type: ATRAnalyzer
    params: { period: 14 }
  - type: TrendAnalyzer
    params: {}

signals:
  - type: PullbackSignal
    requires:
      - EMAAnalyzer
      - TrendAnalyzer
    rules:
      direction: follow_pattern
      min_strength: 0.5

risk:
  algorithm: risk_based
  params:
    risk_pct: 1.0
    min_rr: 2.0
"""


def _write_yaml(tmp: Path, content: str) -> Path:
    p = tmp / "strategy.yaml"
    p.write_text(content)
    return p


class TestLoadStrategy:
    def test_valid_yaml_loads(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, VALID_YAML)
        config = load_strategy(path)
        assert config.name == "test_strategy"
        assert config.version == "2.0"
        assert len(config.analyzers) == 4
        assert len(config.signals) == 1
        assert config.risk.algorithm == "risk_based"

    def test_analyzer_configs(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, VALID_YAML)
        config = load_strategy(path)
        assert config.analyzers[0] == AnalyzerConfig(type="EMAAnalyzer", params={"period": 20})
        assert config.analyzers[1] == AnalyzerConfig(type="EMAAnalyzer", params={"period": 50})
        assert config.analyzers[2] == AnalyzerConfig(type="ATRAnalyzer", params={"period": 14})
        assert config.analyzers[3] == AnalyzerConfig(type="TrendAnalyzer", params={})

    def test_signal_config(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, VALID_YAML)
        config = load_strategy(path)
        sig = config.signals[0]
        assert sig.type == "PullbackSignal"
        assert sig.requires == ("EMAAnalyzer", "TrendAnalyzer")
        assert sig.rules == {"direction": "follow_pattern", "min_strength": 0.5}

    def test_risk_config(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, VALID_YAML)
        config = load_strategy(path)
        assert config.risk == RiskConfig(
            algorithm="risk_based",
            params={"risk_pct": 1.0, "min_rr": 2.0},
        )

    def test_missing_strategy_block(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, "analyzers: []\n")
        with pytest.raises(ConfigError, match="Missing 'strategy' block"):
            load_strategy(path)

    def test_missing_name(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  version: '1.0'\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="Missing 'strategy.name'"):
            load_strategy(path)

    def test_unknown_analyzer_type(self, tmp_path: Path) -> None:
        yaml_str = (
            "strategy:\n  name: test\n" "analyzers:\n  - type: FakeAnalyzer\n    params: {}\n"
        )
        path = _write_yaml(tmp_path, yaml_str)
        config = load_strategy(path)
        errors = validate_config(config)
        assert any("FakeAnalyzer" in e for e in errors)

    def test_non_mapping_yaml(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, "- item1\n- item2\n")
        with pytest.raises(ConfigError, match="Expected YAML mapping"):
            load_strategy(path)

    def test_minimal_yaml(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: minimal\n"
        path = _write_yaml(tmp_path, yaml_str)
        config = load_strategy(path)
        assert config.name == "minimal"
        assert config.version == "1.0"
        assert config.analyzers == ()
        assert config.signals == ()
        assert config.risk == RiskConfig(algorithm="none")

    def test_default_version(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: foo\n"
        path = _write_yaml(tmp_path, yaml_str)
        config = load_strategy(path)
        assert config.version == "1.0"

    def test_default_timeframes(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\n"
        path = _write_yaml(tmp_path, yaml_str)
        config = load_strategy(path)
        assert config.timeframes == ("1d",)

    def test_custom_timeframes(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\n  timeframes:\n    - 1d\n    - 1w\n"
        path = _write_yaml(tmp_path, yaml_str)
        config = load_strategy(path)
        assert config.timeframes == ("1d", "1w")

    def test_single_timeframe(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\n  timeframes:\n    - 1h\n"
        path = _write_yaml(tmp_path, yaml_str)
        config = load_strategy(path)
        assert config.timeframes == ("1h",)

    def test_timeframes_not_a_list(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\n  timeframes: not_a_list\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="'strategy.timeframes' must be a list"):
            load_strategy(path)

    def test_timeframes_in_config_object(self) -> None:
        config = StrategyConfig(name="test", version="1.0", timeframes=("1d", "1w"))
        assert config.timeframes == ("1d", "1w")

    def test_risk_missing_algorithm(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\nrisk:\n  params: {x: 1}\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="missing 'algorithm'"):
            load_strategy(path)

    def test_analyzer_missing_type(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\nanalyzers:\n  - params: {}\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="missing 'type'"):
            load_strategy(path)

    def test_signal_missing_type(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\nsignals:\n  - requires: []\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="missing 'type'"):
            load_strategy(path)


class TestValidateConfig:
    def test_valid_config_no_errors(self) -> None:
        config = StrategyConfig(
            name="test",
            version="1.0",
            analyzers=(AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),),
        )
        assert validate_config(config) == []

    def test_unknown_analyzer_type(self) -> None:
        config = StrategyConfig(
            name="test",
            version="1.0",
            analyzers=(AnalyzerConfig(type="NoSuchAnalyzer", params={}),),
        )
        errors = validate_config(config)
        assert len(errors) == 1
        assert "NoSuchAnalyzer" in errors[0]

    def test_empty_config_no_errors(self) -> None:
        config = StrategyConfig(name="empty", version="1.0")
        assert validate_config(config) == []


class TestBuildAnalyzers:
    def test_builds_correct_instances(self) -> None:
        config = StrategyConfig(
            name="test",
            version="1.0",
            analyzers=(
                AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),
                AnalyzerConfig(type="ATRAnalyzer", params={"period": 14}),
            ),
        )
        analyzers = build_analyzers(config)
        assert len(analyzers) == 2
        assert isinstance(analyzers[0], EMAAnalyzer)
        assert isinstance(analyzers[1], ATRAnalyzer)

    def test_builds_trend_analyzer(self) -> None:
        config = StrategyConfig(
            name="test",
            version="1.0",
            analyzers=(AnalyzerConfig(type="TrendAnalyzer", params={}),),
        )
        analyzers = build_analyzers(config)
        assert isinstance(analyzers[0], TrendAnalyzer)

    def test_unknown_type_raises(self) -> None:
        config = StrategyConfig(
            name="test",
            version="1.0",
            analyzers=(AnalyzerConfig(type="BadType", params={}),),
        )
        with pytest.raises(ConfigError, match="Unknown analyzer type"):
            build_analyzers(config)

    def test_empty_analyzers(self) -> None:
        config = StrategyConfig(name="test", version="1.0")
        assert build_analyzers(config) == []


class TestAnalyzerRegistry:
    def test_registry_contains_known_types(self) -> None:
        assert "EMAAnalyzer" in ANALYZER_TYPES
        assert "ATRAnalyzer" in ANALYZER_TYPES
        assert "TrendAnalyzer" in ANALYZER_TYPES


class TestParseEdgeCases:
    def test_analyzer_not_a_mapping(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\nanalyzers:\n  - not_a_dict\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="must be a mapping"):
            load_strategy(path)

    def test_analyzer_params_not_a_mapping(self, tmp_path: Path) -> None:
        yaml_str = (
            "strategy:\n  name: test\n"
            "analyzers:\n  - type: EMAAnalyzer\n    params: not_a_dict\n"
        )
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="'params' must be a mapping"):
            load_strategy(path)

    def test_analyzers_not_a_list(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\nanalyzers: not_a_list\n"
        path = _write_yaml(tmp_path, yaml_str)
        config = load_strategy(path)
        assert config.analyzers == ()

    def test_signal_not_a_mapping(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\nsignals:\n  - not_a_dict\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="must be a mapping"):
            load_strategy(path)

    def test_signal_requires_not_a_list(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\n" "signals:\n  - type: Sig\n    requires: not_a_list\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="'requires' must be a list"):
            load_strategy(path)

    def test_signal_rules_not_a_mapping(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\n" "signals:\n  - type: Sig\n    rules: not_a_dict\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="'rules' must be a mapping"):
            load_strategy(path)

    def test_signals_not_a_list(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\nsignals: not_a_list\n"
        path = _write_yaml(tmp_path, yaml_str)
        config = load_strategy(path)
        assert config.signals == ()

    def test_risk_not_a_mapping(self, tmp_path: Path) -> None:
        yaml_str = "strategy:\n  name: test\nrisk: not_a_dict\n"
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="'risk' must be a mapping"):
            load_strategy(path)

    def test_risk_params_not_a_mapping(self, tmp_path: Path) -> None:
        yaml_str = (
            "strategy:\n  name: test\n" "risk:\n  algorithm: risk_based\n  params: not_a_dict\n"
        )
        path = _write_yaml(tmp_path, yaml_str)
        with pytest.raises(ConfigError, match="'risk.params' must be a mapping"):
            load_strategy(path)

    def test_validate_signal_requires_unmet(self) -> None:
        config = StrategyConfig(
            name="test",
            version="1.0",
            analyzers=(AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),),
            signals=(SignalConfig(type="Sig", requires=("TrendAnalyzer",), rules={}),),
        )
        errors = validate_config(config)
        assert any("TrendAnalyzer" in e for e in errors)
