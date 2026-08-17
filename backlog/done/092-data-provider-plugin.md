# 092: Extract data providers into a decoupled plugin system

**Status:** pending
**Epic:** data
**Priority:** low
**Depends on:** none

## Description

`data/providers/` (433 lines, 3 providers: dukascopy, yahoo, chain) is
tightly coupled to `data/datastore.py`. Adding a new provider requires
editing the chain provider and the datastore. Providers should be
discoverable and independently testable.

Extract providers into a plugin pattern:

- **`data/providers/base.py`** — `DataProvider` protocol (unchanged)
- **`data/providers/registry.py`** — provider registry, discovery by name
- **`data/providers/dukascopy.py`** — unchanged
- **`data/providers/yahoo.py`** — unchanged
- **`data/providers/chain.py`** — unchanged
- **`data/datastore.py`** — uses registry to resolve provider names

## Design

1. `data/providers/registry.py`:

   ```python
   _PROVIDERS: dict[str, type[DataProvider]] = {}

   def register(name: str, cls: type[DataProvider]) -> None:
       _PROVIDERS[name] = cls

   def get(name: str) -> type[DataProvider]:
       return _PROVIDERS[name]
   ```

2. Each provider module registers itself on import:

   ```python
   # dukascopy.py
   from marketatlas.data.providers.registry import register
   register("dukascopy", DukascopyProvider)
   ```

3. `DataStore` resolves providers via registry instead of hardcoded chain:

   ```python
   provider_cls = get(provider_name)
   provider = provider_cls()
   ```

4. `data/providers/__init__.py` imports all provider modules to trigger
   registration.

5. Tests can register mock providers without touching the chain.

## Acceptance Criteria

- [ ] `data/providers/registry.py` exists with `register`/`get` functions
- [ ] Each provider self-registers on import
- [ ] `DataStore` uses registry, not hardcoded chain
- [ ] `pytest tests/test_providers.py tests/test_dukascopy_provider.py` pass
- [ ] `pytest tests/test_datastore.py` pass
- [ ] Adding a new provider = new file + one `register()` call

## Related

- `src/marketatlas/data/providers/chain.py` — current provider chain
- `src/marketatlas/data/datastore.py` — consumer of providers
- `src/marketatlas/data/providers/base.py` — `DataProvider` protocol
