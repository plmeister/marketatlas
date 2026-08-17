"use strict";
/* global _t */

function _addDays(isoDate, days) {
  return new Date(_t(isoDate) + days * 86400000).toISOString().slice(0, 10);
}

class TradeBoxPrimitive {
  constructor(series, chart, getBoxes) {
    this._series = series;
    this._chart = chart;
    this._getBoxes = getBoxes;
  }

  paneViews() {
    return [
      {
        zOrder: () => "normal",
        renderer: () => ({
          draw: (target) => this._draw(target),
        }),
      },
    ];
  }

  _draw(target) {
    const boxes = this._getBoxes();
    if (!boxes || boxes.length === 0) return;
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const timeScale = this._chart.timeScale();
      const series = this._series;
      for (const b of boxes) {
        const x1 = timeScale.timeToCoordinate(b.fromTime);
        const x2 = timeScale.timeToCoordinate(b.toTime);
        if (x1 === null || x2 === null) continue;
        const x = Math.min(x1, x2);
        const w = Math.abs(x2 - x1);
        const eY = series.priceToCoordinate(b.entry);
        const tY = series.priceToCoordinate(b.target);
        const sY = series.priceToCoordinate(b.stop);
        if (eY === null || tY === null || sY === null) continue;
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = "#22c55e";
        ctx.fillRect(x, Math.min(eY, tY), w, Math.abs(tY - eY));
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = "#ef4444";
        ctx.fillRect(x, Math.min(eY, sY), w, Math.abs(sY - eY));
      }
    });
  }
}

function tradeBoxesAt(cv, frameTime) {
  const candles = cv.model.activeCandles;
  const lastTime = candles.length ? candles[candles.length - 1].time : null;
  const hideFuture = cv.model.futureVisibility === "hide";
  const boxes = [];
  cv.model.trades.forEach((t) => {
    if (t.entry_time > frameTime) return;
    if (t.entry === undefined || t.stop === undefined || t.target === undefined) return;
    let toTime = _addDays(t.entry_time, cv.model.maxHoldDays);
    if (lastTime && _t(toTime) > _t(lastTime)) toTime = lastTime;
    if (hideFuture && _t(toTime) > _t(frameTime)) toTime = frameTime;
    if (_t(toTime) <= _t(t.entry_time)) {
      const nextFrame = cv.model.frames.find((f) => _t(f.time) > _t(frameTime));
      if (!nextFrame) return;
      toTime = nextFrame.time;
    }
    boxes.push({
      fromTime: t.entry_time,
      toTime,
      entry: t.entry,
      stop: t.stop,
      target: t.target,
    });
  });
  return boxes;
}

function updateTrades(cv, idx) {
  const frameTime = cv.model.frameTime(idx);
  if (!frameTime) {
    cv.tradeBoxes = [];
    return;
  }
  cv.tradeBoxes = tradeBoxesAt(cv, frameTime);
}

function hitTradeBox(cv, point) {
  let hit = null;
  for (const b of cv.tradeBoxes) {
    const x1 = cv.chart.timeScale().timeToCoordinate(b.fromTime);
    const x2 = cv.chart.timeScale().timeToCoordinate(b.toTime);
    const eY = cv.candleSeries.priceToCoordinate(b.entry);
    const sY = cv.candleSeries.priceToCoordinate(b.stop);
    const tY = cv.candleSeries.priceToCoordinate(b.target);
    if (x1 === null || x2 === null || eY === null || sY === null || tY === null) continue;
    const xMin = Math.min(x1, x2);
    const xMax = Math.max(x1, x2);
    const yMin = Math.min(eY, sY, tY);
    const yMax = Math.max(eY, sY, tY);
    if (point.x >= xMin && point.x <= xMax && point.y >= yMin && point.y <= yMax) {
      hit = b;
    }
  }
  if (!hit) return null;
  return cv.model.trades.find((t) => t.entry_time === hit.fromTime) || null;
}

function attachTradeBoxes(cv) {
  cv.tradeBoxPrimitive = new TradeBoxPrimitive(
    cv.candleSeries,
    cv.chart,
    () => cv.tradeBoxes,
  );
  cv.candleSeries.attachPrimitive(cv.tradeBoxPrimitive);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    TradeBoxPrimitive,
    tradeBoxesAt,
    updateTrades,
    hitTradeBox,
    attachTradeBoxes,
    _addDays,
  };
} else if (typeof window !== "undefined") {
  window._mav = window._mav || {};
  window._mav.trades = {
    TradeBoxPrimitive,
    tradeBoxesAt,
    updateTrades,
    hitTradeBox,
    attachTradeBoxes,
    _addDays,
  };
}
