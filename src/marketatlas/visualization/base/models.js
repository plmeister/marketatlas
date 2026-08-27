/**
 * AppModel — central state + data access for backtest chart.
 * Pure business logic, no DOM or charting library deps.
 */
function _t(t) {
  return Date.parse(t);
}

// Format a price with magnitude-aware precision (sigfig-like), trimming
// trailing zeros while keeping a sensible floor. 2dp for large prices
// (stocks/crypto), 4dp for mid (forex), 6dp for sub-1 instruments.
function _fmtP(x) {
  if (x === null || x === undefined || !isFinite(x)) return "";
  var ax = Math.abs(x);
  var dp = ax >= 100 ? 2 : ax >= 1 ? 4 : 6;
  var raw = x.toFixed(dp);
  var idx = raw.indexOf(".");
  if (idx === -1) return raw;
  var trimmed = raw.replace(/0+$/, "");
  if (trimmed.charAt(trimmed.length - 1) === ".") trimmed = trimmed.slice(0, -1);
  if (trimmed.indexOf(".") === -1) return x.toFixed(dp);
  var frac = trimmed.slice(idx + 1);
  if (frac.length < 2) return x.toFixed(dp);
  return trimmed;
}

class AppModel {
  constructor(data) {
    // Immutable data
    this.candlesByTF = data.CANDLES_BY_TF || {};
    this.availableTFs = data.AVAILABLE_TFS || [];
    this.frames = data.FRAMES || [];
    this.emaSeries = data.EMA_SERIES || {};
    this.atrData = data.ATR_DATA || [];
    this.srData = data.SR_DATA || [];
    this.trades = data.TRADES || [];
    this.pullbacks = data.PULLBACKS || [];
    this.factsData = data.FACTS_DATA || [];
    this.swingPoints = data.SWING_POINTS || {};
    this.initialBalance = data.INITIAL_BALANCE || 0;
    this.minTouches = data.MIN_TOUCHES || 2;
    this.maxHoldDays = data.MAX_HOLD_DAYS || 10;

    // Primary timeframe (carries overlay data)
    this.tfCandleKey = this.availableTFs.length > 0 ? this.availableTFs[0] : "1d";

    // Backward-compat alias: primary-tf candles (single source of truth).
    // No separate CANDLES blob is emitted; the chart reads activeCandles.
    this.candles = this.candlesByTF[this.tfCandleKey] || data.CANDLES || [];

    // Mutable state
    this.currentFrame = 0;
    this.activeTF = this.tfCandleKey;
    this.playing = false;
    this.playInterval = null;
    this.autoScrollDisabled = false;
    this.programmaticScroll = false;
    this.futureVisibility = "hide"; // 'hide' | 'dim' | 'show'
    this._events = null;
  }

  // --- Candle access ---
  get activeCandles() {
    return this.candlesByTF[this.activeTF] || this.candles;
  }

  isPrimaryTF() {
    return this.activeTF === this.tfCandleKey;
  }

  // --- Frame queries ---
  frameTime(idx) {
    if (idx < 0 || idx >= this.frames.length) return null;
    return this.frames[idx].time;
  }

  frameFacts(idx) {
    if (idx < 0 || idx >= this.factsData.length) return {};
    const facts = this.factsData[idx] || {};
    // Swing facts store pivot *times*; hydrate to full pivot objects once via
    // the shared SWING_POINTS store (deduped serialization).
    const hydrated = {};
    for (const key in facts) {
      if (!Object.prototype.hasOwnProperty.call(facts, key)) continue;
      const fact = facts[key];
      if (fact && fact.type === "swing" && Array.isArray(fact.swings) && this._canHydrate(fact)) {
        const store = this.swingPoints[fact.timeframe || ""] || {};
        hydrated[key] = Object.assign({}, fact, {
          swings: fact.swings.map((t) => store[t]).filter(Boolean),
        });
      } else {
        hydrated[key] = fact;
      }
    }
    return hydrated;
  }

  _canHydrate(fact) {
    // Only hydrate when swing entries are plain time strings (deduped form).
    return fact.swings.length === 0 || typeof fact.swings[0] === "string";
  }

  srLevelsAt(idx) {
    if (idx < 0 || idx >= this.srData.length) return [];
    return this.srData[idx].levels || [];
  }

  evidenceAt(idx) {
    if (idx < 0 || idx >= this.frames.length) return [];
    const f = this.frames[idx];
    const ev = f.evidence || [];
    const risk = f.risk_evidence || [];
    const sigs = (f.signals || []).map((s) => ({
      text:
        "Signal: " +
        s.direction +
        " conf=" +
        (s.confidence || 0).toFixed(2) +
        " (" +
        s.source +
        ")",
      level: "signal",
      source: s.source,
    }));
    const rejections = (f.signal_rejections || []).map((r) => ({
      text: "Rejected: " + (r.text || "no reason"),
      level: "rejection",
      source: r.source || "",
    }));
    return ev.concat(sigs, risk, rejections);
  }

  // --- Trade queries ---
  activeTradesAt(frameTime) {
    return this.trades.filter(
      (t) => t.entry_time <= frameTime && (t.exit_time === null || t.exit_time >= frameTime),
    );
  }

  closedTradesBefore(frameTime) {
    return this.trades.filter((t) => t.exit_time !== null && t.exit_time <= frameTime);
  }

  // --- Significant-event navigation ---
  // Frames that carry signals, risk decisions, or a trade entry/exit.
  // Generic per-frame analyzer evidence is excluded: it exists on every
  // candle, which would make next/prev event navigation step one frame at a
  // time.
  eventIndices() {
    if (!this._events) this._events = this._computeEvents();
    return this._events;
  }

  _computeEvents() {
    const set = new Set();
    this.frames.forEach((f, i) => {
      if (
        (f.risk_evidence && f.risk_evidence.length) ||
        (f.signals && f.signals.length) ||
        (f.signal_rejections && f.signal_rejections.length)
      ) {
        set.add(i);
      }
    });
    this.trades.forEach((t) => {
      [t.entry_time, t.exit_time].forEach((tm) => {
        if (tm === null) return;
        const i = this.frames.findIndex((f) => f.time === tm);
        if (i >= 0) set.add(i);
      });
    });
    return Array.from(set).sort((a, b) => a - b);
  }

  nextEventIndex(fromIdx) {
    const ev = this.eventIndices();
    for (let i = 0; i < ev.length; i++) {
      if (ev[i] > fromIdx) return ev[i];
    }
    return null;
  }

  prevEventIndex(fromIdx) {
    const ev = this.eventIndices();
    for (let i = ev.length - 1; i >= 0; i--) {
      if (ev[i] < fromIdx) return ev[i];
    }
    return null;
  }

  // --- Summary computation ---
  computeSummary(frameTime) {
    let bal = this.initialBalance;
    let wins = 0,
      losses = 0,
      breakevens = 0,
      pnl = 0;
    let grossProfit = 0,
      grossLoss = 0;
    let peak = this.initialBalance,
      worst = 0;

    this.trades.forEach((t) => {
      if (t.exit_time !== null && t.exit_time <= frameTime && t.pnl !== null) {
        bal += t.pnl;
        pnl += t.pnl;
        if (t.result === "win") {
          wins++;
          grossProfit += t.pnl;
        } else if (t.result === "loss") {
          losses++;
          grossLoss += Math.abs(t.pnl);
        } else if (t.result === "breakeven") {
          breakevens++;
        }
      }
      if (bal > peak) peak = bal;
      const dd = peak > 0 ? (peak - bal) / peak : 0;
      if (dd > worst) worst = dd;
    });

    const totalClosed = wins + losses + breakevens;
    const winLossTotal = wins + losses;
    const winRate = winLossTotal > 0 ? (wins / winLossTotal) * 100 : 0;
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;
    const avgWin = wins > 0 ? grossProfit / wins : 0;
    const avgLoss = losses > 0 ? -grossLoss / losses : 0;
    const expectancy = winLossTotal > 0 ? pnl / winLossTotal : 0;
    const returnPct = this.initialBalance > 0 ? (pnl / this.initialBalance) * 100 : 0;

    return {
      balance: bal,
      pnl,
      returnPct,
      wins,
      losses,
      breakevens,
      totalClosed,
      winRate,
      profitFactor,
      avgWin,
      avgLoss,
      expectancy,
      drawdown: worst,
    };
  }

  // --- Move frame ---
  _clamp(idx) {
    if (idx < 0) return 0;
    if (idx >= this.frames.length) return this.frames.length - 1;
    return idx;
  }

  goFirst() {
    this.currentFrame = this._clamp(0);
    return this.currentFrame;
  }
  goLast() {
    this.currentFrame = this._clamp(this.frames.length - 1);
    return this.currentFrame;
  }
  goNext() {
    this.currentFrame = this._clamp(this.currentFrame + 1);
    return this.currentFrame;
  }
  goPrev() {
    this.currentFrame = this._clamp(this.currentFrame - 1);
    return this.currentFrame;
  }
  goTo(idx) {
    this.currentFrame = this._clamp(idx);
    return this.currentFrame;
  }

  // --- Step sizing ---
  // Frames advance on the primary TF (e.g. 1d) while the chart may show a
  // coarser TF (e.g. 1w). Stepping one frame then lands mid-candle and no new
  // candle becomes visible. These helpers return the index that reveals the
  // next/previous candle on the active TF (a step of 1 when TFs match).
  _viewCandles() {
    return this.candlesByTF[this.activeTF] || this.candles;
  }

  nextStepIndex(fromIdx) {
    const curTime = this.frameTime(fromIdx);
    if (curTime === null) return fromIdx;
    const nextBar = this._viewCandles().find((c) => _t(c.time) > _t(curTime));
    if (!nextBar) return this.frames.length - 1;
    for (let i = fromIdx + 1; i < this.frames.length; i++) {
      if (this.frameTime(i) >= nextBar.time) return i;
    }
    return this.frames.length - 1;
  }

  prevStepIndex(fromIdx) {
    const curTime = this.frameTime(fromIdx);
    if (curTime === null) return fromIdx;
    const viewCandles = this._viewCandles();
    let lastVisible = null;
    for (let i = viewCandles.length - 1; i >= 0; i--) {
      if (_t(viewCandles[i].time) <= _t(curTime)) {
        lastVisible = viewCandles[i].time;
        break;
      }
    }
    if (lastVisible === null) return 0;
    for (let i = fromIdx - 1; i >= 0; i--) {
      if (this.frameTime(i) < lastVisible) return i;
    }
    return 0;
  }

  switchTF(tf) {
    if (!this.candlesByTF[tf]) return false;
    this.activeTF = tf;
    return true;
  }

  // --- Future visibility ---
  toggleFutureVisibility() {
    const modes = ["hide", "dim", "show"];
    const idx = (modes.indexOf(this.futureVisibility) + 1) % modes.length;
    this.futureVisibility = modes[idx];
    return this.futureVisibility;
  }
}

// Export for Node tests, attach to window for browser
if (typeof module !== "undefined" && module.exports) {
  module.exports = { AppModel, _t, _fmtP };
} else {
  window.AppModel = AppModel;
  window._t = _t;
  window._fmtP = _fmtP;
}
