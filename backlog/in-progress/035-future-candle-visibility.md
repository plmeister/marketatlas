# 035: Future Candle Visibility

**Status:** pending  
**Epic:** visualisation  
**Priority:** medium

## Description

Candles beyond the current frame cursor represent future data. Should either be hidden or visually distinct to indicate they haven't occurred yet. Prevents confusion about what data was available at decision time.

## Acceptance Criteria

- [ ] Option A: hide future candles entirely (chart ends at current frame)
- [ ] Option B: show future candles dimmed/faded (20-30% opacity)
- [ ] Option C: show future candles with different color (gray/neutral)
- [ ] Default to Option A (hide) — most honest representation
- [ ] Toggle between modes via UI control or keyboard shortcut
- [ ] Info panel shows "Frame X/Y — N candles remaining" indicator
- [ ] Trade markers only shown if trade was known/filled at current frame

## Technical Notes

- `candleSeries.setData()` can be called per-frame with sliced data
- Alternative: use `update()` to modify individual candles' appearance
- Lightweight-charts supports `update()` for real-time updates
- Could add a "replay" vs "analysis" mode toggle

## Related

- `src/marketatlas/visualization/interactive.py` — renderer
- Backlog 034 (current candle visibility)
