# 028: Swing Point Markers on Chart

**Status:** pending  
**Priority:** medium

## Description

Display swing highs/lows as small markers at the high or low of the candle where the swing occurs. Provides visual confirmation of swing detection.

## Acceptance Criteria

- [ ] Swing highs shown as small downward-pointing marker (e.g. `▼` or triangle) at candle high
- [ ] Swing lows shown as small upward-pointing marker (e.g. `▲` or triangle) at candle low
- [ ] Markers only visible for current frame's swing set (respects read-ahead)
- [ ] Markers update when stepping frames
- [ ] Color-coded: blue for support-related lows, orange for resistance-related highs (or similar)
- [ ] Non-intrusive: small size, no chart clutter

## Technical Notes

- Use `chart.addMarkers()` or series marker API from lightweight-charts
- Swing data available in `FACTS_DATA[idx].swing.swings`
- Each swing has `price`, `index` (relative to store), `type` ("high"/"low")

## Related

- `src/marketatlas/visualization/interactive.py` — renderer
- `src/marketatlas/analysis/analyzers/swing.py` — swing detection
- Backlog 026 (separate JS template)
