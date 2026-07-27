# 033: Instrument Registry

**Status:** pending  
**Epic:** data  
**Priority:** high

## Description

Instrument registry maps canonical instrument names to provider-specific symbols. Different providers use different symbols for the same instrument (e.g. Yahoo: `EURUSD=X`, Dukascopy: `EURUSD`, OANDA: `EUR_USD`). Registry provides unified lookup.

## Acceptance Criteria

- [ ] `Instrument` dataclass: canonical name, asset class, description
- [ ] `InstrumentRegistry` stores mappings: `instrument → {provider: symbol}`
- [ ] YAML-based registry file (e.g. `instruments.yaml`)
- [ ] Lookup by canonical name returns provider-specific symbol
- [ ] Reverse lookup: provider symbol → canonical name
- [ ] Validation: warn on missing provider mapping when fetching
- [ ] CLI: `marketatlas instruments list` shows all registered instruments
- [ ] CLI: `marketatlas instruments add` adds new instrument with mappings

## Registry Format

```yaml
instruments:
  EURUSD:
    class: forex
    description: "Euro / US Dollar"
    providers:
      yahoo: "EURUSD=X"
      dukascopy: "EURUSD"
      oanda: "EUR_USD"

  BTCUSD:
    class: crypto
    description: "Bitcoin / US Dollar"
    providers:
      yahoo: "BTC-USD"
      dukascopy: "BTCUSD"
```

## Design

### 1. Instrument Dataclass

```python
@dataclass(frozen=True)
class Instrument:
    canonical: str          # e.g. "EURUSD"
    asset_class: str        # "forex", "crypto", "equity", "commodity"
    description: str
    providers: dict[str, str]  # {provider_name: symbol}
```

### 2. InstrumentRegistry

```python
class InstrumentRegistry:
    def __init__(self, path: Path | None = None): ...
    
    def get(self, canonical: str) -> Instrument | None: ...
    def get_symbol(self, canonical: str, provider: str) -> str | None: ...
    def resolve(self, symbol: str, provider: str) -> str | None:
        """Reverse lookup: provider symbol → canonical name."""
    def list_all(self) -> list[Instrument]: ...
    def add(self, instrument: Instrument) -> None: ...
    def save(self) -> None: ...
```

### 3. Provider Integration

```python
class YahooProvider:
    def __init__(self, registry: InstrumentRegistry | None = None): ...
    
    def fetch(self, instrument: str, ...) -> MarketData:
        # If registry provided, resolve symbol
        # Otherwise, use instrument string directly (backward compat)
```

### 4. Backward Compatibility

- `YahooProvider` works without registry (uses raw symbol string)
- Registry is optional — providers fall back to direct symbol if no mapping
- Existing CLI commands unchanged

### 5. Tests

- Registry loads YAML correctly
- Lookup by canonical name returns correct provider symbol
- Reverse lookup works
- Missing symbol returns None
- Provider works with and without registry
- YAML round-trip: load → save → load produces same data

## Related

- `src/marketatlas/data/providers/base.py` — DataProvider interface
- `src/marketatlas/data/providers/yahoo.py` — YahooProvider
- Backlog 032: Dukascopy provider
- `src/marketatlas/data/types.py` — Symbol type
