# 034: Frame Stepper — Current Candle Visibility

**Status:** pending  
**Epic:** visualisation  
**Priority:** medium

## Description

When stepping through frames, ensure the candle at the current cursor is always visible on chart. Currently the chart may show a fixed viewport that doesn't track the frame cursor.

## Acceptance Criteria

- [ ] Chart auto-scrolls so current frame's candle is visible
- [ ] Current candle highlighted (border, background, or crosshair snap)
- [ ] Smooth scroll animation when stepping frames (not jarring jump)
- [ ] Play mode: chart scrolls naturally as frames advance
- [ ] User can still manually pan/zoom without fighting auto-scroll
- [ ] Auto-scroll can be toggled off (pinch/scroll disables until re-enabled)

## Technical Notes

- Use `chart.timeScale().scrollToPosition()` or `scrollToTime()`
- May need to track user interaction state to avoid fighting manual pan
- Current candle marker: vertical line or background highlight

## Related

- `src/marketatlas/visualization/interactive.py` — renderer
- Backlog 028 (swing markers)
- Backlog 035 (future candle visibility)
