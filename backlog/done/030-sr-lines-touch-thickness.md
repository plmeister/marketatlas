# 030: S/R Horizontal Lines with Touch-Based Thickness

**Status:** pending  
**Epic:** visualisation  
**Priority:** medium

## Description

Display support/resistance levels as horizontal lines on chart. Line thickness scales with number of touches. Filter: only show levels with touches >= configurable minimum (default: 2).

## Acceptance Criteria

- [ ] S/R levels shown as horizontal lines spanning visible chart area
- [ ] Line thickness proportional to touch count (1px per touch, or tiered: 2 touches=1px, 3+=2px, 5+=3px)
- [ ] Color: blue for support, orange/resistance for resistance
- [ ] Configurable `min_touches` parameter (default: 2) — levels below threshold hidden
- [ ] `min_touches` configurable in strategy YAML or renderer config
- [ ] Lines update per frame (read-ahead safe)
- [ ] Line label shows price and touch count
- [ ] Current S/R data has many single-touch levels — filter reduces noise significantly

## Technical Notes

- S/R data in `SR_DATA[idx].levels`
- Each level has `price`, `strength` (touch count), `type` ("support"/"resistance")
- Many levels currently have `strength: 1` — filtering these cleans up chart significantly
- Use `createPriceLine()` for each level, or custom line series
- `min_touches` should be parameter on renderer or strategy config

## Related

- `src/marketatlas/analysis/analyzers/support_resistance.py` — S/R detection
- `src/marketatlas/visualization/interactive.py` — renderer
- Backlog 026 (separate JS template)
