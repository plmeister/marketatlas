# 041: Separate Capability, Provider and Definition

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Refine AST type system while model is still small. Clarify three distinct concepts currently conflated in `Definition`:

- **Capability**: what an analysis node does (e.g. "compute EMA", "detect pullback")
- **Provider**: how a capability is implemented (e.g. `EMAAnalyzer`, `PullbackSignal`)
- **Definition**: a named instance of a provider bound to specific parameters (e.g. "ema20", "ema50")

## Acceptance Criteria

- [ ] `Capability` dataclass: `id: str`, `description: str`, `required_params: tuple[str, ...]`
- [ ] `Provider` dataclass: `name: str`, `capability: str`, `impl: str`, `params: tuple[Parameter, ...]`
- [ ] `Definition` simplified: references provider + provides instance params + bindings
- [ ] Multiple providers can advertise same capability (e.g. `SMA(20)` and `EMA(20)`)
- [ ] Backward compat: existing builder API still works (may delegate internally)
- [ ] Terminology document updated (backlog 044)

## Rationale

Makes provider binding much easier later. A strategy says "I need an EMA(20)" not "I need EMAAnalyzer(period=20)". The registry (backlog 043) resolves provider choice.

## Related

- Backlog 036: AST model (will be refactored)
- Backlog 043: Provider registry
- Backlog 044: Semantic model document
