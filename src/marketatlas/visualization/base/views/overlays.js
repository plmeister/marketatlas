"use strict";

function clearPriceLines(cv) {
  if (cv.candleSeries) {
    cv.srPriceLines.forEach((pl) => cv.candleSeries.removePriceLine(pl));
  }
  cv.srPriceLines = [];
}

function updateEMAs(cv, idx) {
  if (!cv.model.isPrimaryTF() || !cv.candleSeries) return;
  const frameTime = cv.model.frameTime(idx);
  if (!frameTime) return;
  Object.entries(cv.model.emaSeries).forEach(([name, data]) => {
    const sliced = data.filter((d) => d.time <= frameTime);
    if (cv.emaSeriesMap[name]) cv.emaSeriesMap[name].setData(sliced);
  });
}

function updateSR(cv, idx) {
  clearPriceLines(cv);
  const levels = cv.model.srLevelsAt(idx);
  cv._srHits = [];
  levels.forEach((lv) => {
    if (lv.strength < cv.model.minTouches) return;
    const isSupport = lv.type === "support";
    const color = isSupport ? "#3b82f6" : "#f59e0b";
    const lineWidth = lv.strength >= 5 ? 3 : lv.strength >= 3 ? 2 : 1;
    const pl = cv.candleSeries.createPriceLine({
      price: lv.price,
      color,
      lineWidth,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: (isSupport ? "S" : "R") + " " + _fmtP(lv.price) + " (" + lv.strength + ")",
    });
    cv.srPriceLines.push(pl);
    cv._srHits.push({ price: lv.price, strength: lv.strength, type: lv.type });
  });
}

function updateZigzag(cv, idx) {
  if (!cv.zigzagBull || !cv.zigzagBear) return;
  cv.zigzagBull.applyOptions({ lineVisible: false });
  cv.zigzagBear.applyOptions({ lineVisible: false });

  const facts = cv.model.frameFacts(idx);
  Object.values(facts).forEach((val) => {
    if (val.type !== "swingstructure") return;
    const points = val.points;
    const lineData = [];
    points.forEach((p) => {
      lineData.push({ time: p.time, value: p.price });
    });
    if (lineData.length < 2) return;
    const series = val.direction === "bullish" ? cv.zigzagBull : cv.zigzagBear;
    series.setData(lineData);
    series.applyOptions({ lineVisible: true });
  });
}

function createAnnotationSeries(cv, tf) {
  const m = cv.model;
  if (tf !== m.tfCandleKey) return;
  const emaColors = {
    EMA10: "#a855f7",
    EMA20: "#3b82f6",
    EMA50: "#f59e0b",
    EMA200: "#ec4899",
  };
  Object.keys(m.emaSeries).forEach((name) => {
    const s = cv.chart.addLineSeries({
      color: emaColors[name] || "#888",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    cv.emaSeriesMap[name] = s;
  });
  cv.zigzagBull = cv.chart.addLineSeries({
    color: "#22c55e",
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
    lineVisible: false,
  });
  cv.zigzagBear = cv.chart.addLineSeries({
    color: "#ef4444",
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
    lineVisible: false,
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    clearPriceLines,
    updateEMAs,
    updateSR,
    updateZigzag,
    createAnnotationSeries,
  };
} else if (typeof window !== "undefined") {
  window._mav = window._mav || {};
  window._mav.overlays = {
    clearPriceLines,
    updateEMAs,
    updateSR,
    updateZigzag,
    createAnnotationSeries,
  };
}
