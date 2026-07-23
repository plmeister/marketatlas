# Strategy Configuration Loader

**Epic:** strategy

## Problem

No way to define strategies in config. Analysis graph, signal rules, and risk parameters are all hardcoded. Need YAML-based strategy definitions so strategies are data, not code.

## Goal

Load a YAML strategy file that defines the analysis graph (which analyzers, with what params), signal conditions, and risk/sizing parameters. Produce a ready-to-run `StrategyConfig` object that the backtester consumes.

## Design

### 1. Config Schema

File: `src/marketatlas/strategy/config.py`

```python
@dataclass(frozen=True)
class AnalyzerConfig:
    type: str              # e.g. "EMAAnalyzer"
    params: dict[str, Any] # e.g. {"period": 20}

@dataclass(frozen=True)
class SignalConfig:
    type: str                          # e.g. "PullbackSignal"
    requires: tuple[str, ...]          # analyzer instance keys this signal reads
    rules: dict[str, Any]              # signal-specific parameters

@dataclass(frozen=True)
class RiskConfig:
    algorithm: str            # e.g. "risk_based"
    params: dict[str, Any]    # algorithm-specific

@dataclass(frozen=True)
class StrategyConfig:
    name: str
    version: str
    analyzers: tuple[AnalyzerConfig, ...]
    signals: tuple[SignalConfig, ...]
    risk: RiskConfig
```

### 2. Loader

File: `src/marketatlas/strategy/loader.py`

```python
def load_strategy(path: Path) -> StrategyConfig:
    """Load YAML strategy file into StrategyConfig."""

def validate_config(config: StrategyConfig) -> list[str]:
    """Validate config: unknown analyzer types, missing params, etc."""
```

### 3. Analyzer Registry Integration

The loader maps analyzer type strings to classes:

```python
ANALYZER_TYPES: dict[str, type[Analyzer]] = {
    "EMAAnalyzer": EMAAnalyzer,
    "ATRAnalyzer": ATRAnalyzer,
    "TrendAnalyzer": TrendAnalyzer,
    "SwingStructureAnalyzer": SwingStructureAnalyzer,
    "FourSwingPullbackDetector": FourSwingPullbackDetector,
    "SupportResistanceAnalyzer": SupportResistanceAnalyzer,
}
```

Unknown types raise `ConfigError`. Params are passed as `**kwargs` to the constructor.

### 4. Example YAML

```yaml
strategy:
  name: pullback_4swing
  version: "1.0"

analyzers:
  - type: EMAAnalyzer
    params: { period: 20 }
  - type: EMAAnalyzer
    params: { period: 50 }
  - type: ATRAnalyzer
    params: { period: 14 }
  - type: TrendAnalyzer
    params: {}
  - type: SwingStructureAnalyzer
    params: { min_swing_atr: 0.3 }
  - type: FourSwingPullbackDetector
    params:
      max_deviation_pct: 0.15
      min_swing_separation_atr: 0.3
      confirmation:
        min_body_pct: 0.6
        min_volume_ratio: 1.2
  - type: SupportResistanceAnalyzer
    params: { lookback: 100 }

signals:
  - type: PullbackSignal
    requires:
      - FourSwingPullbackDetector
      - TrendAnalyzer
    rules:
      direction: follow_pattern
      min_strength: 0.5

risk:
  algorithm: risk_based
  params:
    risk_pct: 1.0
    min_rr: 2.0
    max_rr: 4.0
    max_stop_atr: 3.0
    avoid_srxing: true
```

### 5. Design Constraints

- Config is immutable (`frozen=True` dataclasses)
- Unknown analyzer types → `ConfigError` at load time, not at runtime
- YAML is the only supported format (no JSON/TOML loading)
- Loader is pure function: `Path → StrategyConfig`

### 6. Tests

- Valid YAML loads correctly
- Missing required field → `ConfigError`
- Unknown analyzer type → `ConfigError`
- Invalid param types → `ConfigError`
- Round-trip: config → dataclass fields match YAML

## Evidence

- `load_strategy(path)` returns `StrategyConfig` with correct fields
- Invalid configs fail fast with clear error messages
