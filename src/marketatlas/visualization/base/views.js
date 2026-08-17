/**
 * Views — display layer over AppModel.
 * ChartView delegates to sub-modules; other views stay here.
 * Requires _t() global from models.js.
 */
/* global _t */

// --- Sub-module loading ---
var _chart, _overlays, _markers, _trades, _crosshair;
if (typeof require === "function") {
  _chart = require("./views/chart");
  _overlays = require("./views/overlays");
  _markers = require("./views/markers");
  _trades = require("./views/trades");
  _crosshair = require("./views/crosshair");
} else {
  _chart = window._mav.chart;
  _overlays = window._mav.overlays;
  _markers = window._mav.markers;
  _trades = window._mav.trades;
  _crosshair = window._mav.crosshair;
}

// --- ChartView ---
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

  // --- Chart lifecycle ---
  _chartOpts(container, height) {
    return _chart.chartOpts(this, container, height);
  }

  destroy() {
    _overlays.clearPriceLines(this);
    if (this._tooltipEl && this._tooltipEl.parentNode) {
      this._tooltipEl.parentNode.removeChild(this._tooltipEl);
    }
    this._tooltipEl = null;
    if (this.candleSeries && this.tradeBoxPrimitive) {
      this.candleSeries.detachPrimitive(this.tradeBoxPrimitive);
    }
    this.tradeBoxPrimitive = null;
    _chart.destroyCharts(this);
    this.candleSeries = null;
    this.emaSeriesMap = {};
    this.zigzagBull = null;
    this.zigzagBear = null;
    this.atrSeries = null;
    this.volumeSeries = null;
  }

  build(tf) {
    this.destroy();
    _chart.buildChart(this, tf);
    _trades.attachTradeBoxes(this);
    _overlays.createAnnotationSeries(this, tf);
    this.containers.main.style.position = "relative";
    this.chart.subscribeCrosshairMove((param) => _crosshair.onCrosshairMove(this, param));
  }

  // --- Frame-level updates ---
  updateCandles(idx) { _chart.updateCandles(this, idx); }
  highlightCandle(idx) { _chart.highlightCandle(this, idx); }
  updateVolume(idx) { _chart.updateVolume(this, idx); }
  updateATR(idx) { _chart.updateATR(this, idx); }
  setCrosshair(idx) { _chart.setCrosshair(this, idx); }
  scrollToFrame(idx) { _chart.scrollToFrame(this, idx); }
  resize() { _chart.resize(this); }
  getVisibleTimeRange() { return _chart.getVisibleTimeRange(this); }
  setVisibleTimeRange(range) { _chart.setVisibleTimeRange(this, range); }

  // --- Overlays ---
  updateEMAs(idx) { _overlays.updateEMAs(this, idx); }
  updateSR(idx) { _overlays.updateSR(this, idx); }
  updateZigzag(idx) { _overlays.updateZigzag(this, idx); }

  // --- Markers ---
  updateMarkers(idx) { _markers.updateMarkers(this, idx); }

  // --- Trades ---
  updateTrades(idx) {
    this._frameIdx = idx;
    _overlays.updateSR(this, idx);
    _trades.updateTrades(this, idx);
  }
}

ChartView.TradeBoxPrimitive = _trades.TradeBoxPrimitive;

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
