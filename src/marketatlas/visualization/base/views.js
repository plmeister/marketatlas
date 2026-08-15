/**
 * Views — display layer over AppModel.
 * Each view owns DOM elements and updates from model state.
 * Requires _t() global from models.js.
 */
/* global _t */

// --- ChartView: LightweightCharts lifecycle ---
// Add whole days to a 'YYYY-MM-DD' date via pure UTC ms arithmetic.
function _addDays(isoDate, days) {
  return new Date(_t(isoDate) + days * 86400000).toISOString().slice(0, 10);
}

// Custom series primitive drawing semi-transparent trade zone rectangles.
// v4.1.3 has no Rectangle series type, so boxes are rendered on canvas via
// attachPrimitive + a pane renderer.
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
    const media = target.useMediaCoordinateSpace();
    const ctx = media.context;
    const timeScale = this._chart.timeScale();
    const series = this._series;
    ctx.save();
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
      // Reward zone: entry <-> target (flips below entry for shorts).
      ctx.globalAlpha = 0.3;
      ctx.fillStyle = "#22c55e";
      ctx.fillRect(x, Math.min(eY, tY), w, Math.abs(tY - eY));
      // Risk zone: entry <-> stop (flips above entry for shorts).
      ctx.globalAlpha = 0.3;
      ctx.fillStyle = "#ef4444";
      ctx.fillRect(x, Math.min(eY, sY), w, Math.abs(sY - eY));
    }
    ctx.restore();
  }
}

class ChartView {
  constructor(model, containers) {
    this.model = model;
    this.containers = containers;
    this.chart = null;
    this.candleSeries = null;
    this.emaSeriesMap = {};
    this.zigzagBull = null;
    this.zigzagBear = null;
    this.atrChart = null;
    this.atrSeries = null;
    this.volumeChart = null;
    this.volumeSeries = null;
    this.srPriceLines = [];
    this.tradeBoxes = [];
    this.tradeBoxPrimitive = null;
    this._tooltipEl = null;
    this._lastSeriesLen = 0;
  }

  _chartOpts(container, height) {
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

  destroy() {
    this._clearPriceLines();
    if (this._tooltipEl && this._tooltipEl.parentNode) {
      this._tooltipEl.parentNode.removeChild(this._tooltipEl);
    }
    this._tooltipEl = null;
    if (this.candleSeries && this.tradeBoxPrimitive) {
      this.candleSeries.detachPrimitive(this.tradeBoxPrimitive);
    }
    this.tradeBoxPrimitive = null;
    if (this.chart) {
      this.chart.remove();
      this.chart = null;
    }
    if (this.atrChart) {
      this.atrChart.remove();
      this.atrChart = null;
    }
    if (this.volumeChart) {
      this.volumeChart.remove();
      this.volumeChart = null;
    }
    this.candleSeries = null;
    this.emaSeriesMap = {};
    this.zigzagBull = null;
    this.zigzagBear = null;
    this.atrSeries = null;
    this.volumeSeries = null;
  }

  _clearPriceLines() {
    // lightweight-charts 4.1.3: lines have no remove(); detach via the series.
    if (this.candleSeries) {
      this.srPriceLines.forEach((pl) => this.candleSeries.removePriceLine(pl));
    }
    this.srPriceLines = [];
  }

  build(tf) {
    this.destroy();
    const m = this.model;
    const candles = m.activeCandles;

    // Main chart
    this.chart = LightweightCharts.createChart(
      this.containers.main,
      this._chartOpts(this.containers.main, 500),
    );
    this.candleSeries = this.chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    this.candleSeries.setData(candles);

    // Trade zone rectangles (semi-transparent overlay via custom primitive)
    this.tradeBoxPrimitive = new TradeBoxPrimitive(
      this.candleSeries,
      this.chart,
      () => this.tradeBoxes,
    );
    this.candleSeries.attachPrimitive(this.tradeBoxPrimitive);

    // Overlays (only on primary TF)
    if (tf === m.tfCandleKey) {
      const emaColors = {
        EMA10: "#a855f7",
        EMA20: "#3b82f6",
        EMA50: "#f59e0b",
        EMA200: "#ec4899",
      };
      Object.keys(m.emaSeries).forEach((name) => {
        const s = this.chart.addLineSeries({
          color: emaColors[name] || "#888",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        this.emaSeriesMap[name] = s;
      });
      this.zigzagBull = this.chart.addLineSeries({
        color: "#22c55e",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        lineVisible: false,
      });
      this.zigzagBear = this.chart.addLineSeries({
        color: "#ef4444",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        lineVisible: false,
      });
    }

    // ATR panel
    this.atrChart = LightweightCharts.createChart(
      this.containers.atr,
      this._chartOpts(this.containers.atr, 120),
    );
    this.atrSeries = this.atrChart.addLineSeries({
      color: "#8b5cf6",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "ATR",
    });
    this.atrSeries.setData(tf === m.tfCandleKey ? m.atrData : []);

    // Volume panel
    this.volumeChart = LightweightCharts.createChart(
      this.containers.volume,
      this._chartOpts(this.containers.volume, 80),
    );
    this.volumeSeries = this.volumeChart.addHistogramSeries({
      priceLineVisible: false,
      lastValueVisible: false,
    });
    this.volumeSeries.setData(
      candles.map((c) => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)",
      })),
    );

    // Time scale sync
    const sync = (src, t1, t2) => {
      src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) {
          t1.timeScale().setVisibleLogicalRange(range);
          t2.timeScale().setVisibleLogicalRange(range);
        }
      });
    };
    sync(this.chart, this.atrChart, this.volumeChart);
    sync(this.atrChart, this.chart, this.volumeChart);
    sync(this.volumeChart, this.chart, this.atrChart);

    // Auto-scroll disable on manual pan/zoom (main chart only)
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      if (m.programmaticScroll) {
        m.programmaticScroll = false;
        return;
      }
      if (!m.playing) {
        m.autoScrollDisabled = true;
        this._updateAutoBtn(false);
      }
    });

    // Trade-box hover tooltip
    this.containers.main.style.position = "relative";
    this.chart.subscribeCrosshairMove((param) => this._onCrosshairMove(param));
  }

  _updateAutoBtn(active) {
    const btn = document.getElementById("btn-autoscroll");
    if (btn) btn.classList.toggle("active", active);
  }

  // --- Frame-level updates ---
  updateCandles(idx) {
    const frameTime = this.model.frameTime(idx);
    if (!frameTime) return;
    const all = this.model.activeCandles;
    const mode = this.model.futureVisibility;
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
    this.candleSeries.setData(data);
  }

  highlightCandle(idx) {
    const frameTime = this.model.frameTime(idx);
    if (!frameTime) return;
    const candle = this.model.activeCandles.find((c) => c.time === frameTime);
    if (candle) {
      this.candleSeries.update({
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

  updateVolume(idx) {
    const frameTime = this.model.frameTime(idx);
    if (!frameTime) return;
    const all = this.model.activeCandles;
    const mode = this.model.futureVisibility;
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
    this.volumeSeries.setData(data);
  }

  updateEMAs(idx) {
    if (!this.model.isPrimaryTF() || !this.candleSeries) return;
    const frameTime = this.model.frameTime(idx);
    if (!frameTime) return;
    Object.entries(this.model.emaSeries).forEach(([name, data]) => {
      const sliced = data.filter((d) => d.time <= frameTime);
      if (this.emaSeriesMap[name]) this.emaSeriesMap[name].setData(sliced);
    });
  }

  updateATR(idx) {
    if (!this.model.isPrimaryTF()) return;
    const frameTime = this.model.frameTime(idx);
    if (!frameTime) return;
    this.atrSeries.setData(this.model.atrData.filter((d) => d.time <= frameTime));
  }

  updateSR(idx) {
    this._clearPriceLines();
    const levels = this.model.srLevelsAt(idx);
    levels.forEach((lv) => {
      if (lv.strength < this.model.minTouches) return;
      const isSupport = lv.type === "support";
      const color = isSupport ? "#3b82f6" : "#f59e0b";
      const lineWidth = lv.strength >= 5 ? 3 : lv.strength >= 3 ? 2 : 1;
      const pl = this.candleSeries.createPriceLine({
        price: lv.price,
        color,
        lineWidth,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: (isSupport ? "S" : "R") + " " + lv.price.toFixed(0) + " (" + lv.strength + ")",
      });
      this.srPriceLines.push(pl);
    });
  }

  updateTrades(idx) {
    this.updateSR(idx);
    const frameTime = this.model.frameTime(idx);
    if (!frameTime) {
      this.tradeBoxes = [];
      return;
    }
    this.tradeBoxes = this._tradeBoxesAt(frameTime);
  }

  // Trade boxes visible in every frame after placement: from the entry date to
  // entry + max hold days (clamped to the last candle). Vertical span covers
  // stop->target; the primitive splits it into reward (entry->target) and risk
  // (entry->stop) zones.
  _tradeBoxesAt(frameTime) {
    const candles = this.model.activeCandles;
    const lastTime = candles.length ? candles[candles.length - 1].time : null;
    const boxes = [];
    this.model.trades.forEach((t) => {
      if (t.entry_time > frameTime) return;
      if (t.entry === undefined || t.stop === undefined || t.target === undefined) return;
      let toTime = _addDays(t.entry_time, this.model.maxHoldDays);
      if (lastTime && _t(toTime) > _t(lastTime)) toTime = lastTime;
      if (toTime <= t.entry_time) return;
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

  // --- Trade-box hover tooltip ---
  _onCrosshairMove(param) {
    if (!param || !param.point) {
      this._hideTradeTooltip();
      return;
    }
    const trade = this._hitTradeBox(param.point);
    if (!trade) {
      this._hideTradeTooltip();
      return;
    }
    this._showTradeTooltip(trade, param.point);
  }

  // Hit-test crosshair against the current trade boxes; overlapping boxes pick
  // the last (drawn topmost).
  _hitTradeBox(point) {
    let hit = null;
    for (const b of this.tradeBoxes) {
      const x1 = this.chart.timeScale().timeToCoordinate(b.fromTime);
      const x2 = this.chart.timeScale().timeToCoordinate(b.toTime);
      const eY = this.candleSeries.priceToCoordinate(b.entry);
      const sY = this.candleSeries.priceToCoordinate(b.stop);
      const tY = this.candleSeries.priceToCoordinate(b.target);
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
    return this.model.trades.find((t) => t.entry_time === hit.fromTime) || null;
  }

  _ensureTooltipEl() {
    if (this._tooltipEl) return this._tooltipEl;
    const el = document.createElement("div");
    Object.assign(el.style, {
      position: "absolute",
      zIndex: 10,
      pointerEvents: "none",
      display: "none",
      background: "rgba(10,10,20,0.92)",
      color: "#e0e0e0",
      border: "1px solid #0f3460",
      borderRadius: "4px",
      padding: "6px 8px",
      font: "11px/1.5 ui-monospace, Menlo, monospace",
      whiteSpace: "nowrap",
    });
    this.containers.main.appendChild(el);
    this._tooltipEl = el;
    return el;
  }

  _showTradeTooltip(trade, point) {
    const el = this._ensureTooltipEl();
    const isBull = trade.direction === "bullish";
    const resolved = trade.exit_time !== null && trade.result !== null;
    const row = (label, value) =>
      '<div><span style="color:#94a3b8">' + label + "</span> " + value + "</div>";
    el.innerHTML =
      '<div style="font-weight:700;color:#e94560;margin-bottom:4px">' +
      (isBull ? "LONG" : "SHORT") +
      (trade.source ? " \u00b7 " + trade.source : "") +
      "</div>" +
      row("Entry", trade.entry.toFixed(2)) +
      row("Stop", trade.stop.toFixed(2)) +
      row("Target", trade.target.toFixed(2)) +
      row("R:R", (trade.rr_ratio || 0).toFixed(2)) +
      row("Risk", "$" + (trade.risk_amount || 0).toFixed(2)) +
      row("Win", "$" + ((trade.rr_ratio || 0) * (trade.risk_amount || 0)).toFixed(2)) +
      (resolved
        ? '<div style="margin-top:4px;color:' +
          (trade.result === "win" ? "#22c55e" : "#ef4444") +
          '">' +
          trade.result.toUpperCase() +
          " " +
          (trade.pnl >= 0 ? "+" : "-") +
          "$" +
          Math.abs(trade.pnl).toFixed(2) +
          "</div>"
        : "");
    el.style.display = "block";
    const cw = this.containers.main.clientWidth;
    const ch = this.containers.main.clientHeight;
    let left = point.x + 14;
    let top = point.y + 14;
    if (left + (el.offsetWidth || 0) > cw - 4) {
      left = point.x - (el.offsetWidth || 0) - 10;
    }
    if (top + (el.offsetHeight || 0) > ch - 4) {
      top = point.y - (el.offsetHeight || 0) - 10;
    }
    el.style.left = left + "px";
    el.style.top = top + "px";
  }

  _hideTradeTooltip() {
    if (this._tooltipEl) this._tooltipEl.style.display = "none";
  }

  updateZigzag(idx) {
    if (!this.zigzagBull || !this.zigzagBear) return;
    this.zigzagBull.applyOptions({ lineVisible: false });
    this.zigzagBear.applyOptions({ lineVisible: false });

    const facts = this.model.frameFacts(idx);
    Object.values(facts).forEach((val) => {
      if (val.type !== "swingstructure") return;
      const points = val.points;
      const lineData = [];
      points.forEach((p) => {
        lineData.push({ time: p.time, value: p.price });
      });
      if (lineData.length < 2) return;
      const series = val.direction === "bullish" ? this.zigzagBull : this.zigzagBear;
      series.setData(lineData);
      series.applyOptions({ lineVisible: true });
    });
  }

  updateMarkers(idx) {
    const frameTime = this.model.frameTime(idx);
    if (!frameTime) return;
    const markers = [];

    // Current candle
    markers.push({
      time: frameTime,
      position: "belowBar",
      color: "#facc15",
      shape: "diamond",
      text: "",
    });

    // Pullback
    const pb = this.model.pullbacks[idx];
    if (pb) {
      markers.push({
        time: pb.time,
        position: pb.position,
        color: pb.color,
        shape: pb.shape,
      });
    }

    // Swing markers — only show swings detected on the active TF. Swings from
    // other timeframes (e.g. 1w swings on a 1d view) stay hidden; each TF's
    // swings carry their own native candle time so markers align to the right
    // bars on their own TF.
    const facts = this.model.frameFacts(idx);
    const activeTF = this.model.activeTF;
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

    // Trade markers — resolution only (win/loss circle); entry is drawn as a
    // box by the trade-zone primitive.
    this.model.trades.forEach((t) => {
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
    this.candleSeries.setMarkers(markers);
  }

  setCrosshair(idx) {
    const frameTime = this.model.frameTime(idx);
    if (!frameTime) return;
    const candle = this.model.activeCandles.find((c) => c.time === frameTime);
    if (candle) {
      this.chart.setCrosshairPosition(candle.close, candle.time, this.candleSeries);
    }
  }

  scrollToFrame(idx) {
    if (idx < 0 || idx >= this.model.frames.length) return;
    const frameTime = this.model.frameTime(idx);
    if (frameTime === null) return;
    const seriesData = this.candleSeries.data();
    const seriesIdx = seriesData.findIndex((d) => d.time === frameTime);
    const range = this.chart.timeScale().getVisibleLogicalRange();
    const visibleBars = range && range.to - range.from > 0 ? range.to - range.from : 40;
    if (seriesIdx < 0) {
      this.model.programmaticScroll = true;
      this.chart.timeScale().scrollToTime(frameTime);
      return;
    }
    // When future candles are hidden the series shrinks/grows each step; the
    // stored logical range then can point past the series end and the chart
    // renders blank. Re-anchor whenever the series length changed.
    const margin = Math.max(2, visibleBars * 0.2);
    if (
      seriesData.length === this._lastSeriesLen &&
      range &&
      seriesIdx >= range.from + margin &&
      seriesIdx <= range.to - margin
    ) {
      return; // frame already comfortably visible
    }
    this._lastSeriesLen = seriesData.length;
    const from = Math.max(0, seriesIdx - visibleBars * 0.2);
    this.model.programmaticScroll = true;
    this.chart.timeScale().setVisibleLogicalRange({ from, to: from + visibleBars });
  }

  resize() {
    if (this.chart) this.chart.applyOptions({ width: this.containers.main.clientWidth });
    if (this.atrChart) this.atrChart.applyOptions({ width: this.containers.atr.clientWidth });
    if (this.volumeChart)
      this.volumeChart.applyOptions({
        width: this.containers.volume.clientWidth,
      });
  }

  getVisibleTimeRange() {
    if (!this.chart) return null;
    return this.chart.timeScale().getVisibleRange();
  }

  setVisibleTimeRange(range) {
    if (!this.chart || !range) return;
    this.chart.timeScale().setVisibleRange(range);
  }
}

// --- InfoPanelView ---
class InfoPanelView {
  constructor(containerId) {
    this.el = document.getElementById(containerId);
  }

  update(model, idx) {
    const frameTime = model.frameTime(idx);
    if (!frameTime) {
      this.el.innerHTML = "No data.";
      return;
    }
    const facts = model.frameFacts(idx);
    let html = "";

    html += "<h3>Frame " + (idx + 1) + "/" + model.frames.length + "</h3>";
    const d = new Date(_t(frameTime));
    html +=
      '<div class="row"><span class="label">Date</span><span class="value">' +
      d.toISOString().slice(0, 10) +
      "</span></div>";

    const remaining = model.activeCandles.filter((c) => c.time > frameTime).length;
    html +=
      '<div class="row"><span class="label">Remaining</span><span class="value">' +
      remaining +
      " candles</span></div>";

    const candle = model.activeCandles.find((c) => c.time === frameTime);
    if (candle) {
      [
        ["O", "open"],
        ["H", "high"],
        ["L", "low"],
        ["C", "close"],
      ].forEach(([label, key]) => {
        html +=
          '<div class="row"><span class="label">' +
          label +
          '</span><span class="value">' +
          candle[key].toFixed(2) +
          "</span></div>";
      });
      html +=
        '<div class="row"><span class="label">Vol</span><span class="value">' +
        candle.volume.toFixed(0) +
        "</span></div>";
    }

    // Balance
    let bal = model.initialBalance;
    model.trades.forEach((t) => {
      if (t.exit_time !== null && t.exit_time <= frameTime && t.pnl !== null) bal += t.pnl;
    });
    html +=
      '<div class="row"><span class="label">Balance</span><span class="value">' +
      bal.toFixed(2) +
      "</span></div>";

    // Indicators
    html += "<h3>Indicators</h3>";
    Object.entries(facts).forEach(([key, val]) => {
      if (val.type === "ema") {
        html +=
          '<div class="row"><span class="label">' +
          key +
          '</span><span class="value">' +
          val.value.toFixed(2) +
          "</span></div>";
      } else if (val.type === "atr") {
        html +=
          '<div class="row"><span class="label">' +
          key +
          '</span><span class="value">' +
          val.value.toFixed(2) +
          "</span></div>";
      } else if (val.type === "trend") {
        const cls =
          val.direction === "bullish" ? "bull" : val.direction === "bearish" ? "bear" : "neutral";
        html +=
          '<div class="row"><span class="label">Trend</span><span class="value ' +
          cls +
          '">' +
          val.direction.toUpperCase() +
          " (" +
          val.strength.toFixed(2) +
          ")</span></div>";
      }
    });

    // S/R
    const srLevels = model.srLevelsAt(idx).filter((lv) => lv.strength >= model.minTouches);
    if (srLevels.length) {
      html += "<h3>S/R Levels</h3>";
      srLevels.forEach((lv) => {
        const cls = lv.type === "support" ? "sr-support" : "sr-resistance";
        html +=
          '<div class="row"><span class="label ' +
          cls +
          '">' +
          (lv.type === "support" ? "S" : "R") +
          '</span><span class="value">' +
          lv.price.toFixed(0) +
          " (" +
          lv.strength +
          ")</span></div>";
      });
    }

    // Active / last trade
    const active = model.activeTradesAt(frameTime);
    if (active.length) {
      html += "<h3>Trade</h3>";
      active.forEach((t) => {
        html +=
          '<div class="row"><span class="label">Status</span><span class="value trade-open">OPEN ' +
          (t.direction === "bullish" ? "LONG" : "SHORT") +
          "</span></div>";
        html +=
          '<div class="row"><span class="label">Entry</span><span class="value">' +
          t.entry.toFixed(2) +
          "</span></div>";
        html +=
          '<div class="row"><span class="label">Stop</span><span class="value">' +
          t.stop.toFixed(2) +
          "</span></div>";
        html +=
          '<div class="row"><span class="label">Target</span><span class="value">' +
          t.target.toFixed(2) +
          "</span></div>";
        html +=
          '<div class="row"><span class="label">Size</span><span class="value">' +
          t.size.toFixed(4) +
          "</span></div>";
        html +=
          '<div class="row"><span class="label">R:R</span><span class="value">' +
          t.rr_ratio.toFixed(1) +
          "</span></div>";
      });
    } else {
      const closed = model.closedTradesBefore(frameTime);
      if (closed.length) {
        const last = closed[closed.length - 1];
        const cls = last.result === "win" ? "bull" : last.result === "loss" ? "bear" : "neutral";
        html += "<h3>Last Trade</h3>";
        html +=
          '<div class="row"><span class="label">Result</span><span class="value ' +
          cls +
          '">' +
          (last.result || "open").toUpperCase() +
          "</span></div>";
        html +=
          '<div class="row"><span class="label">P&amp;L</span><span class="value ' +
          cls +
          '">' +
          (last.pnl >= 0 ? "+" : "") +
          last.pnl.toFixed(2) +
          "</span></div>";
      }
    }

    this.el.innerHTML = html;
  }
}

// --- EvidencePanelView ---
class EvidencePanelView {
  constructor(containerId) {
    this.el = document.getElementById(containerId);
  }

  update(model, idx) {
    const evidence = model.evidenceAt(idx);
    if (!evidence.length) {
      this.el.innerHTML =
        idx < model.frames.length ? "No evidence for this frame." : "No evidence.";
      return;
    }
    this.el.innerHTML = evidence
      .map((e) => {
        const cls = "ev-" + e.level;
        const src = e.source ? ' <span class="ev-source">(' + e.source + ")</span>" : "";
        return '<div class="ev-entry ' + cls + '">' + e.text + src + "</div>";
      })
      .join("");
  }
}

// --- SummaryBarView ---
class SummaryBarView {
  update(model, idx) {
    const frameTime = model.frameTime(idx);
    if (!frameTime) return;
    const s = model.computeSummary(frameTime);
    document.getElementById("s-balance").textContent = s.balance.toFixed(2);
    const pnlEl = document.getElementById("s-pnl");
    pnlEl.textContent = (s.pnl >= 0 ? "+" : "") + s.pnl.toFixed(2);
    pnlEl.className = s.pnl >= 0 ? "pnl-pos" : "pnl-neg";
    const retEl = document.getElementById("s-return");
    retEl.textContent = s.returnPct.toFixed(1) + "%";
    retEl.className = s.returnPct >= 0 ? "pnl-pos" : "pnl-neg";
    document.getElementById("s-trades").textContent = String(s.totalClosed);
    document.getElementById("s-breakevens").textContent = String(s.breakevens);
    const wr = s.winRate.toFixed(0) + "%";
    document.getElementById("s-winrate").textContent = wr;
    document.getElementById("s-pf").textContent =
      s.profitFactor === Infinity ? "\u221e" : s.profitFactor.toFixed(2);
    document.getElementById("s-avgwin").textContent = s.avgWin.toFixed(2);
    document.getElementById("s-avgloss").textContent = s.avgLoss.toFixed(2);
    document.getElementById("s-expectancy").textContent =
      (s.expectancy >= 0 ? "$" : "-$") + Math.abs(s.expectancy).toFixed(2);
    document.getElementById("s-drawdown").textContent = (s.drawdown * 100).toFixed(1) + "%";
  }
}

// --- TimelineBarView ---
class TimelineBarView {
  constructor(containerId) {
    this.el = document.getElementById(containerId);
  }

  build(model) {
    const candles = model.activeCandles;
    if (!candles.length) {
      this.el.innerHTML = "";
      return;
    }
    const minTime = _t(candles[0].time);
    const maxTime = _t(candles[candles.length - 1].time);
    const span = maxTime - minTime || 1;
    let html = "";
    model.trades.forEach((t, i) => {
      const startPct = (((_t(t.entry_time) - minTime) / span) * 100).toFixed(2);
      const endPct =
        t.exit_time !== null ? (((_t(t.exit_time) - minTime) / span) * 100).toFixed(2) : "100";
      const width = Math.max(parseFloat(endPct) - parseFloat(startPct), 0.3);
      const cls =
        t.result === "win"
          ? "tl-win"
          : t.result === "loss"
            ? "tl-loss"
            : t.result === "breakeven"
              ? "tl-breakeven"
              : "tl-open";
      html +=
        '<div class="timeline-trade ' +
        cls +
        '" style="left:' +
        startPct +
        "%;width:" +
        width +
        '%" title="Trade ' +
        (i + 1) +
        ": " +
        (t.result || "open") +
        " PnL: " +
        (t.pnl !== null ? t.pnl.toFixed(2) : "open") +
        '"></div>';
    });
    html += '<div class="timeline-cursor" id="timeline-cursor" style="left:0%"></div>';
    this.el.innerHTML = html;
  }

  updateCursor(model, idx) {
    const cursor = document.getElementById("timeline-cursor");
    if (!cursor || !model.activeCandles.length) return;
    const frameTime = model.frameTime(idx);
    if (!frameTime) return;
    const minTime = _t(model.activeCandles[0].time);
    const maxTime = _t(model.activeCandles[model.activeCandles.length - 1].time);
    const span = maxTime - minTime || 1;
    cursor.style.left = (((_t(frameTime) - minTime) / span) * 100).toFixed(2) + "%";
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    ChartView,
    InfoPanelView,
    EvidencePanelView,
    SummaryBarView,
    TimelineBarView,
  };
} else {
  window.ChartView = ChartView;
  window.InfoPanelView = InfoPanelView;
  window.EvidencePanelView = EvidencePanelView;
  window.SummaryBarView = SummaryBarView;
  window.TimelineBarView = TimelineBarView;
}
