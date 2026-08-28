"use strict";
/* global _t */

function updateMarkers(cv, idx) {
  const frameTime = cv.model.frameTime(idx);
  if (!frameTime) return;
  const markers = [];

  markers.push({
    time: frameTime,
    position: "belowBar",
    color: "#facc15",
    shape: "diamond",
    text: "",
  });

  const pb = cv.model.pullbacks[idx];
  if (pb) {
    markers.push({
      time: pb.time,
      position: pb.position,
      color: pb.color,
      shape: pb.shape,
    });
  }

  const facts = cv.model.frameFacts(idx);
  const activeTF = cv.model.activeTF;
  Object.values(facts).forEach((val) => {
    if (val.type === "swing" && val.swings && val.timeframe === activeTF) {
      val.swings.forEach((sw) => {
        if (!sw.time) return;
        const isHigh = sw.type === "high";
        markers.push({
          time: sw.time,
          position: isHigh ? "aboveBar" : "belowBar",
          color: isHigh ? "#f59e0b" : "#3b82f6",
          shape: isHigh ? "arrowDown" : "arrowUp",
          text: "",
        });
      });
    }
  });

  cv.model.trades.forEach((t) => {
    if (t.entry_time !== null && t.entry_time <= frameTime) {
      markers.push({
        time: t.entry_time,
        position: t.direction === "bearish" ? "belowBar" : "aboveBar",
        color: "#a855f7",
        shape: "square",
        text: "",
      });
    }
    if (t.exit_time !== null && t.exit_time <= frameTime) {
      const isWin = t.result === "win";
      markers.push({
        time: t.exit_time,
        position: isWin ? "aboveBar" : "belowBar",
        color: isWin ? "#22c55e" : "#ef4444",
        shape: "circle",
        text: (isWin ? "+" : "") + (t.pnl || 0).toFixed(2),
      });
    }
  });
  markers.sort((a, b) => _t(a.time) - _t(b.time));
  cv.candleSeries.setMarkers(markers);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { updateMarkers };
} else if (typeof window !== "undefined") {
  window._mav = window._mav || {};
  window._mav.markers = { updateMarkers };
}
