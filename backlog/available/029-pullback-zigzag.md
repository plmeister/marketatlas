# 029: Pullback Pattern Zigzag Line

**Status:** pending  
**Epic:** visualisation  
**Priority:** medium

## Description

Display detected pullback pattern as a zigzag line connecting the swings that make up the pattern. Shows the 4-swing structure visually on the chart.

## Acceptance Criteria

- [ ] Zigzag line connects swing points that form the pullback pattern (e.g. L1→H1→L2→H2 for bullish)
- [ ] Line only shown when pullback detected (not for invalidated/neutral)
- [ ] Line updates per frame — shows pattern relevant to current frame only
- [ ] Line color: green for bullish pullback, red for bearish pullback
- [ ] Line style: solid, width 2-3px for visibility
- [ ] Endpoints extend slightly beyond swing markers for clarity
- [ ] Pattern swings differ from general swing markers (see backlog 028)

## Technical Notes

- Pullback data in `FACTS_DATA[idx].four_swing_pullback`
- `swing_pattern` array contains the swing points forming the pattern
- Each swing has `price`, `index`, `type`
- Use `chart.addLineSeries()` or draw API for the zigzag
- Coordinate mapping: swing index → candle timestamp → chart x-position

## Related

- `src/marketatlas/analysis/signals/pullback_signal.py` — pullback detection
- `src/marketatlas/analysis/detectors/four_swing_pullback.py` — pattern logic
- Backlog 028 (swing markers)
- Backlog 026 (separate JS template)
