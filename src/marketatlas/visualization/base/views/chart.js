"use strict";

function _updateAutoBtn(active) {
  const btn = document.getElementById("btn-autoscroll");
  if (btn) btn.classList.toggle("active", active);
}

function _pricePrecision(m) {
  let has = false,
    maxAx = 0;
  Object.values(m.candlesByTF || {}).forEach((cs) => {
    cs.forEach((c) => {
      const ax = Math.max(Math.abs(c.low), Math.abs(c.high));
      if (ax > maxAx) maxAx = ax;
      has = true;
    });
  });
  if (!has) return 2;
  return maxAx >= 100 ? 2 : maxAx >= 1 ? 4 : 6;
}

function chartOpts(cv, container, height) {
  return {
    width: container.clientWidth,
    height,
    layout: { background: { color: "#1a1a2e" }, textColor: "#e0e0e0" },
    grid: {
      vertLines: { color: "#1e2a3a" },
      horzLines: { color: "#1e2a3a" },
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: { borderColor: "#0f3460", timeVisible: true },
    rightPriceScale: { borderColor: "#0f3460" },
  };
}

function buildChart(cv, tf) {
  const m = cv.model;
  const candles = m.activeCandles;

  cv.chart = LightweightCharts.createChart(
    cv.containers.main,
    chartOpts(cv, cv.containers.main, 500),
  );
  cv.candleSeries = cv.chart.addCandlestickSeries({
    upColor: "#22c55e",
    downColor: "#ef4444",
    borderUpColor: "#22c55e",
    borderDownColor: "#ef4444",
    wickUpColor: "#22c55e",
    wickDownColor: "#ef4444",
    priceFormat: {
      type: "price",
      precision: _pricePrecision(m),
      minMove: 1 / Math.pow(10, _pricePrecision(m)),
    },
  });
  cv.candleSeries.setData(candles);

  cv.atrChart = LightweightCharts.createChart(
    cv.containers.atr,
    chartOpts(cv, cv.containers.atr, 120),
  );
  cv.atrSeries = cv.atrChart.addLineSeries({
    color: "#8b5cf6",
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: true,
    title: "ATR",
  });
  cv.atrSeries.setData(tf === m.tfCandleKey ? m.atrData : []);

  cv.volumeChart = LightweightCharts.createChart(
    cv.containers.volume,
    chartOpts(cv, cv.containers.volume, 80),
  );
  cv.volumeSeries = cv.volumeChart.addHistogramSeries({
    priceLineVisible: false,
    lastValueVisible: false,
  });
  cv.volumeSeries.setData(
    candles.map((c) => ({
      time: c.time,
      value: c.volume,
      color: c.close >= c.open ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)",
    })),
  );

  const sync = (src, t1, t2) => {
    src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) {
        t1.timeScale().setVisibleLogicalRange(range);
        t2.timeScale().setVisibleLogicalRange(range);
      }
    });
  };
  sync(cv.chart, cv.atrChart, cv.volumeChart);
  sync(cv.atrChart, cv.chart, cv.volumeChart);
  sync(cv.volumeChart, cv.chart, cv.atrChart);

  cv.chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
    if (m.programmaticScroll) {
      m.programmaticScroll = false;
      return;
    }
    if (!m.playing) {
      m.autoScrollDisabled = true;
      _updateAutoBtn(false);
    }
  });
}

function destroyCharts(cv) {
  if (cv.chart) {
    cv.chart.remove();
    cv.chart = null;
  }
  if (cv.atrChart) {
    cv.atrChart.remove();
    cv.atrChart = null;
  }
  if (cv.volumeChart) {
    cv.volumeChart.remove();
    cv.volumeChart = null;
  }
}

function updateCandles(cv, idx) {
  const frameTime = cv.model.frameTime(idx);
  if (!frameTime) return;
  const all = cv.model.activeCandles;
  const mode = cv.model.futureVisibility;
  let data;
  if (mode === "hide") {
    data = all.filter((c) => c.time <= frameTime);
  } else if (mode === "dim") {
    data = all.map((c) =>
      c.time > frameTime
        ? {
            ...c,
            color: "rgba(128,128,128,0.3)",
            borderColor: "rgba(128,128,128,0.3)",
            wickColor: "rgba(128,128,128,0.3)",
          }
        : c,
    );
  } else {
    data = all;
  }
  cv.candleSeries.setData(data);
}

function highlightCandle(cv, idx) {
  const frameTime = cv.model.frameTime(idx);
  if (!frameTime) return;
  const candle = cv.model.activeCandles.find((c) => c.time === frameTime);
  if (candle) {
    cv.candleSeries.update({
      time: candle.time,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
      borderColor: "#facc15",
      wickColor: "#facc15",
    });
  }
}

function updateVolume(cv, idx) {
  const frameTime = cv.model.frameTime(idx);
  if (!frameTime) return;
  const all = cv.model.activeCandles;
  const mode = cv.model.futureVisibility;
  const color = (c) => (c.close >= c.open ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)");
  const dimColor = "rgba(128,128,128,0.2)";
  let data;
  if (mode === "hide") {
    data = all
      .filter((c) => c.time <= frameTime)
      .map((c) => ({ time: c.time, value: c.volume, color: color(c) }));
  } else if (mode === "dim") {
    data = all.map((c) => ({
      time: c.time,
      value: c.volume,
      color: c.time > frameTime ? dimColor : color(c),
    }));
  } else {
    data = all.map((c) => ({
      time: c.time,
      value: c.volume,
      color: color(c),
    }));
  }
  cv.volumeSeries.setData(data);
}

function updateATR(cv, idx) {
  if (!cv.model.isPrimaryTF()) return;
  const frameTime = cv.model.frameTime(idx);
  if (!frameTime) return;
  cv.atrSeries.setData(cv.model.atrData.filter((d) => d.time <= frameTime));
}

function setCrosshair(cv, idx) {
  const frameTime = cv.model.frameTime(idx);
  if (!frameTime) return;
  const candle = cv.model.activeCandles.find((c) => c.time === frameTime);
  if (candle) {
    cv.chart.setCrosshairPosition(candle.close, candle.time, cv.candleSeries);
  }
}

function scrollToFrame(cv, idx) {
  if (idx < 0 || idx >= cv.model.frames.length) return;
  const frameTime = cv.model.frameTime(idx);
  if (frameTime === null) return;
  const seriesData = cv.candleSeries.data();
  const seriesIdx = seriesData.findIndex((d) => d.time === frameTime);
  const range = cv.chart.timeScale().getVisibleLogicalRange();
  const visibleBars = range && range.to - range.from > 0 ? range.to - range.from : 40;
  if (seriesIdx < 0) {
    cv.model.programmaticScroll = true;
    cv.chart.timeScale().scrollToTime(frameTime);
    return;
  }
  const margin = Math.max(2, visibleBars * 0.2);
  if (
    seriesData.length === cv._lastSeriesLen &&
    range &&
    seriesIdx >= range.from + margin &&
    seriesIdx <= range.to - margin
  ) {
    return;
  }
  cv._lastSeriesLen = seriesData.length;
  const from = Math.max(0, seriesIdx - visibleBars * 0.2);
  cv.model.programmaticScroll = true;
  cv.chart.timeScale().setVisibleLogicalRange({ from, to: from + visibleBars });
}

function resize(cv) {
  if (cv.chart) cv.chart.applyOptions({ width: cv.containers.main.clientWidth });
  if (cv.atrChart) cv.atrChart.applyOptions({ width: cv.containers.atr.clientWidth });
  if (cv.volumeChart)
    cv.volumeChart.applyOptions({
      width: cv.containers.volume.clientWidth,
    });
}

function getVisibleTimeRange(cv) {
  if (!cv.chart) return null;
  return cv.chart.timeScale().getVisibleRange();
}

function setVisibleTimeRange(cv, range) {
  if (!cv.chart || !range) return;
  cv.chart.timeScale().setVisibleRange(range);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    chartOpts,
    _pricePrecision,
    buildChart,
    destroyCharts,
    updateCandles,
    highlightCandle,
    updateVolume,
    updateATR,
    setCrosshair,
    scrollToFrame,
    resize,
    getVisibleTimeRange,
    setVisibleTimeRange,
  };
} else if (typeof window !== "undefined") {
  window._mav = window._mav || {};
  window._mav.chart = {
    chartOpts,
    buildChart,
    destroyCharts,
    updateCandles,
    highlightCandle,
    updateVolume,
    updateATR,
    setCrosshair,
    scrollToFrame,
    resize,
    getVisibleTimeRange,
    setVisibleTimeRange,
  };
}
