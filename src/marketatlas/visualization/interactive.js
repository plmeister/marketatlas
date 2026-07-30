const CANDLES = null; // @data:CANDLES
const FRAMES = null; // @data:FRAMES
const EMA_SERIES = null; // @data:EMA_SERIES
const ATR_DATA = null; // @data:ATR_DATA
const SR_DATA = null; // @data:SR_DATA
const TRADES = null; // @data:TRADES
const PULLBACKS = null; // @data:PULLBACKS
const FACTS_DATA = null; // @data:FACTS_DATA
const EVIDENCE_MAP = null; // @data:EVIDENCE_MAP
const SUMMARY = null; // @data:SUMMARY
const INITIAL_BALANCE = null; // @data:INITIAL_BALANCE
const MIN_TOUCHES = null; // @data:MIN_TOUCHES

let currentFrame = 0;
let playing = false;
let playInterval = null;
let autoScrollDisabled = false;
let programmaticScroll = false;
let futureVisibility = 'hide'; // 'hide' | 'dim' | 'show'

// --- Chart setup ---
const chartContainer = document.getElementById('chart-container');
const chart = LightweightCharts.createChart(chartContainer, {
  width: chartContainer.clientWidth,
  height: 500,
  layout: { background: { color: '#1a1a2e' }, textColor: '#e0e0e0' },
  grid: { vertLines: { color: '#1e2a3a' }, horzLines: { color: '#1e2a3a' } },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  timeScale: { borderColor: '#0f3460', timeVisible: true },
  rightPriceScale: { borderColor: '#0f3460' },
});

const candleSeries = chart.addCandlestickSeries({
  upColor: '#22c55e', downColor: '#ef4444',
  borderUpColor: '#22c55e', borderDownColor: '#ef4444',
  wickUpColor: '#22c55e', wickDownColor: '#ef4444',
});
candleSeries.setData(CANDLES);

const emaColors = { EMA10: '#a855f7', EMA20: '#3b82f6', EMA50: '#f59e0b', EMA200: '#ec4899' };
const emaSeriesMap = {};
Object.keys(EMA_SERIES).forEach(name => {
  const s = chart.addLineSeries({
    color: emaColors[name] || '#888',
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
  });
  emaSeriesMap[name] = s;
});

// Pullback zigzag line series
const zigzagBull = chart.addLineSeries({
  color: '#22c55e', lineWidth: 2,
  priceLineVisible: false, lastValueVisible: false,
  lineVisible: false,
});
const zigzagBear = chart.addLineSeries({
  color: '#ef4444', lineWidth: 2,
  priceLineVisible: false, lastValueVisible: false,
  lineVisible: false,
});

// ATR panel
const atrContainer = document.getElementById('atr-container');
const atrChart = LightweightCharts.createChart(atrContainer, {
  width: atrContainer.clientWidth,
  height: 120,
  layout: { background: { color: '#1a1a2e' }, textColor: '#e0e0e0' },
  grid: { vertLines: { color: '#1e2a3a' }, horzLines: { color: '#1e2a3a' } },
  timeScale: { borderColor: '#0f3460', timeVisible: true },
  rightPriceScale: { borderColor: '#0f3460' },
});
const atrLine = atrChart.addLineSeries({
  color: '#8b5cf6', lineWidth: 1,
  priceLineVisible: false, lastValueVisible: true, title: 'ATR',
});

// Volume histogram panel
const volumeContainer = document.getElementById('volume-container');
const volumeChart = LightweightCharts.createChart(volumeContainer, {
  width: volumeContainer.clientWidth,
  height: 80,
  layout: { background: { color: '#1a1a2e' }, textColor: '#e0e0e0' },
  grid: { vertLines: { color: '#1e2a3a' }, horzLines: { color: '#1e2a3a' } },
  timeScale: { borderColor: '#0f3460', timeVisible: true },
  rightPriceScale: { borderColor: '#0f3460' },
});
const volumeSeries = volumeChart.addHistogramSeries({
  priceLineVisible: false,
  lastValueVisible: false,
});
volumeSeries.setData(CANDLES.map(c => ({
  time: c.time, value: c.volume,
  color: c.close >= c.open ? 'rgba(34,197,94,0.5)' : 'rgba(239,68,68,0.5)',
})));

// Sync time scales
chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
  if (range) { atrChart.timeScale().setVisibleLogicalRange(range); volumeChart.timeScale().setVisibleLogicalRange(range); }
});
atrChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
  if (range) { chart.timeScale().setVisibleLogicalRange(range); volumeChart.timeScale().setVisibleLogicalRange(range); }
});
volumeChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
  if (range) { chart.timeScale().setVisibleLogicalRange(range); atrChart.timeScale().setVisibleLogicalRange(range); }
});

// --- S/R price lines management ---
let srPriceLines = [];
function clearSR() {
  srPriceLines.forEach(pl => {
    try { candleSeries.removePriceLine(pl); } catch(e) {}
  });
  srPriceLines = [];
}
function updateSR(frameIdx) {
  clearSR();
  if (frameIdx >= SR_DATA.length) return;
  const levels = SR_DATA[frameIdx].levels;
  levels.forEach(lv => {
    if (lv.strength < MIN_TOUCHES) return;
    const isSupport = lv.type === 'support';
    const color = isSupport ? '#3b82f6' : '#f59e0b';
    let lineWidth;
    if (lv.strength >= 5) lineWidth = 3;
    else if (lv.strength >= 3) lineWidth = 2;
    else lineWidth = 1;
    const pl = candleSeries.createPriceLine({
      price: lv.price,
      color: color,
      lineWidth: lineWidth,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: (isSupport ? 'S' : 'R') + ' ' + lv.price.toFixed(0) + ' (' + lv.strength + ')',
    });
    srPriceLines.push(pl);
  });
}

// --- Trade price lines management ---
let tradePriceLines = [];
function clearTrades() {
  tradePriceLines.forEach(pl => {
    try { candleSeries.removePriceLine(pl); } catch(e) {}
  });
  tradePriceLines = [];
}
function updateTradeLines(frameIdx) {
  clearTrades();
  if (frameIdx >= FRAMES.length) return;
  const frameTime = FRAMES[frameIdx].time;
  TRADES.forEach(t => {
    const notExited = t.exit_time === null || t.exit_time >= frameTime;
    const isActive = t.entry_time <= frameTime && notExited;
    if (!isActive) return;
    const entryColor = t.direction === 'bullish' ? '#22c55e' : '#ef4444';
    const stopColor = '#ef4444';
    const targetColor = '#22c55e';
    tradePriceLines.push(candleSeries.createPriceLine({
      price: t.entry, color: entryColor, lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true, title: 'Entry ' + t.entry.toFixed(2),
    }));
    tradePriceLines.push(candleSeries.createPriceLine({
      price: t.stop, color: stopColor, lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true, title: 'Stop ' + t.stop.toFixed(2),
    }));
    tradePriceLines.push(candleSeries.createPriceLine({
      price: t.target, color: targetColor, lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true, title: 'Target ' + t.target.toFixed(2),
    }));
  });
}

// --- Candle highlight ---
function updateCandleHighlight(frameIdx) {
  if (frameIdx >= FRAMES.length) return;
  const time = FRAMES[frameIdx].time;
  const candle = CANDLES.find(c => c.time === time);
  if (candle) {
    candleSeries.update({
      time: candle.time,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
      borderColor: '#facc15',
      wickColor: '#facc15',
    });
  }
}

// --- Zigzag management ---
function updateZigzag(frameIdx) {
  zigzagBull.applyOptions({ lineVisible: false });
  zigzagBear.applyOptions({ lineVisible: false });
  if (frameIdx >= FACTS_DATA.length) return;
  const facts = FACTS_DATA[frameIdx] || {};
  Object.values(facts).forEach(val => {
    if (val.type !== 'pullback') return;
    if (val.status !== 'detected' && val.status !== 'confirmed') return;
    const indices = val.swing_pattern_indices || [];
    const prices = val.swing_pattern || [];
    if (indices.length < 2) return;
    const lineData = indices.map((idx, i) => ({
      time: CANDLES[idx] ? CANDLES[idx].time : null,
      value: prices[i],
    })).filter(p => p.time !== null);
    if (lineData.length < 2) return;
    const series = val.direction === 'bullish' ? zigzagBull : zigzagBear;
    series.setData(lineData);
    series.applyOptions({ lineVisible: true });
  });
}
function updateMarkers(frameIdx) {
  const markers = [];
  // Current candle diamond marker
  if (frameIdx < FRAMES.length) {
    markers.push({
      time: FRAMES[frameIdx].time,
      position: 'belowBar',
      color: '#facc15',
      shape: 'diamond',
      text: '',
    });
  }
  if (frameIdx < PULLBACKS.length && PULLBACKS[frameIdx]) {
    const pb = PULLBACKS[frameIdx];
    markers.push({
      time: pb.time,
      position: pb.position,
      color: pb.color,
      shape: pb.shape,
      text: pb.text,
    });
  }
  // Swing point markers
  const facts = FACTS_DATA[frameIdx] || {};
  Object.values(facts).forEach(val => {
    if (val.type === 'swing' && val.swings) {
      val.swings.forEach(sw => {
        const candleTime = CANDLES[sw.index] ? CANDLES[sw.index].time : null;
        if (candleTime === null) return;
        const isHigh = sw.type === 'high';
        markers.push({
          time: candleTime,
          position: isHigh ? 'aboveBar' : 'belowBar',
          color: isHigh ? '#f59e0b' : '#3b82f6',
          shape: isHigh ? 'arrowDown' : 'arrowUp',
          text: '',
        });
      });
    }
  });
  // Trade entry markers
  TRADES.forEach(t => {
    if (t.entry_time <= FRAMES[frameIdx].time) {
      const isBull = t.direction === 'bullish';
      markers.push({
        time: t.entry_time,
        position: isBull ? 'belowBar' : 'aboveBar',
        color: '#22c55e',
        shape: isBull ? 'arrowUp' : 'arrowDown',
        text: t.source,
      });
    }
    if (t.exit_time !== null && t.exit_time <= FRAMES[frameIdx].time) {
      const isWin = t.result === 'win';
      markers.push({
        time: t.exit_time,
        position: isWin ? 'aboveBar' : 'belowBar',
        color: isWin ? '#22c55e' : '#ef4444',
        shape: 'circle',
        text: (isWin ? '+' : '') + (t.pnl || 0).toFixed(2),
      });
    }
  });
  markers.sort((a, b) => a.time - b.time);
  candleSeries.setMarkers(markers);
}

// --- Info panel ---
function updateInfoPanel(frameIdx) {
  const panel = document.getElementById('info-content');
  if (frameIdx >= FRAMES.length) { panel.innerHTML = 'No data.'; return; }
  const frame = FRAMES[frameIdx];
  const facts = FACTS_DATA[frameIdx] || {};
  let html = '';

  html += '<h3>Frame ' + (frameIdx + 1) + '/' + FRAMES.length + '</h3>';
  const d = new Date(frame.time * 1000);
  html += '<div class="row"><span class="label">Date</span><span class="value">' +
          d.toISOString().slice(0, 10) + '</span></div>';

  // Remaining candles
  const remaining = CANDLES.filter(c => c.time > frame.time).length;
  html += '<div class="row"><span class="label">Remaining</span><span class="value">' +
          remaining + ' candles</span></div>';

  // Find candle OHLCV from candles
  const candle = CANDLES.find(c => c.time === frame.time);
  if (candle) {
    html += '<div class="row"><span class="label">O</span><span class="value">' +
            candle.open.toFixed(2) + '</span></div>';
    html += '<div class="row"><span class="label">H</span><span class="value">' +
            candle.high.toFixed(2) + '</span></div>';
    html += '<div class="row"><span class="label">L</span><span class="value">' +
            candle.low.toFixed(2) + '</span></div>';
    html += '<div class="row"><span class="label">C</span><span class="value">' +
            candle.close.toFixed(2) + '</span></div>';
    html += '<div class="row"><span class="label">Vol</span><span class="value">' +
            candle.volume.toFixed(0) + '</span></div>';
  }

  // Balance from summary (cumulative)
  let bal = INITIAL_BALANCE;
  TRADES.forEach(t => {
    if (t.exit_time !== null && t.exit_time <= frame.time && t.pnl !== null) {
      bal += t.pnl;
    }
  });
  html += '<div class="row"><span class="label">Balance</span><span class="value">' +
          bal.toFixed(2) + '</span></div>';

  // Indicators
  html += '<h3>Indicators</h3>';
  Object.entries(facts).forEach(([key, val]) => {
    if (val.type === 'ema') {
      html += '<div class="row"><span class="label">' + key + '</span><span class="value">' +
              val.value.toFixed(2) + '</span></div>';
    } else if (val.type === 'atr') {
      html += '<div class="row"><span class="label">' + key + '</span><span class="value">' +
              val.value.toFixed(2) + '</span></div>';
    } else if (val.type === 'trend') {
      const cls = val.direction === 'bullish' ? 'bull' :
                  val.direction === 'bearish' ? 'bear' : 'neutral';
      html += '<div class="row"><span class="label">Trend</span><span class="value ' + cls + '">' +
              val.direction.toUpperCase() + ' (' + val.strength.toFixed(2) + ')</span></div>';
    }
  });

  // Pullback
  Object.entries(facts).forEach(([key, val]) => {
    if (val.type === 'pullback') {
      html += '<h3>Pattern</h3>';
      const statusColor = val.status === 'confirmed' ? 'bull' :
                          val.status === 'invalidated' ? 'bear' : 'neutral';
      html += '<div class="row"><span class="label">' + key + '</span><span class="value ' +
              statusColor + '">' + val.status.toUpperCase() + '</span></div>';
      if (val.swing_pattern && val.swing_pattern.length > 0) {
        html += '<div class="row"><span class="label">Pattern</span><span class="value">' +
                val.swing_pattern.map(p => p.toFixed(0)).join('/') + '</span></div>';
      }
      if (val.deviation_pct > 0) {
        html += '<div class="row"><span class="label">Deviation</span><span class="value">' +
                val.deviation_pct.toFixed(1) + '%</span></div>';
      }
      if (val.confirmation_strength > 0) {
        html += '<div class="row"><span class="label">Confirmation</span><span class="value">' +
                (val.confirmation_strength * 100).toFixed(0) + '%</span></div>';
      }
    }
  });

  // S/R levels
  if (frameIdx < SR_DATA.length) {
    const srLevels = SR_DATA[frameIdx].levels.filter(lv => lv.strength >= MIN_TOUCHES);
    if (srLevels.length > 0) {
      html += '<h3>S/R Levels</h3>';
      srLevels.forEach(lv => {
        const cls = lv.type === 'support' ? 'sr-support' : 'sr-resistance';
        const label = lv.type === 'support' ? 'S' : 'R';
        html += '<div class="row"><span class="label ' + cls + '">' +
                label + '</span><span class="value">' +
                lv.price.toFixed(0) + ' (' + lv.strength +
                ')</span></div>';
      });
    }
  }

  // Active trade
  const activeTrades = TRADES.filter(t =>
    t.entry_time <= frame.time && (t.exit_time === null || t.exit_time >= frame.time)
  );
  if (activeTrades.length > 0) {
    html += '<h3>Trade</h3>';
    activeTrades.forEach(t => {
      const dirLabel = t.direction === 'bullish' ? 'LONG' : 'SHORT';
      html += '<div class="row"><span class="label">Status</span>' +
              '<span class="value trade-open">OPEN ' +
              dirLabel + '</span></div>';
      html += '<div class="row"><span class="label">Entry</span><span class="value">' +
              t.entry.toFixed(2) + '</span></div>';
      html += '<div class="row"><span class="label">Stop</span><span class="value">' +
              t.stop.toFixed(2) + '</span></div>';
      html += '<div class="row"><span class="label">Target</span><span class="value">' +
              t.target.toFixed(2) + '</span></div>';
      html += '<div class="row"><span class="label">Size</span><span class="value">' +
              t.size.toFixed(4) + '</span></div>';
      html += '<div class="row"><span class="label">R:R</span><span class="value">' +
              t.rr_ratio.toFixed(1) + '</span></div>';
    });
  } else {
    // Show last closed trade if any
    const closedTrades = TRADES.filter(t =>
      t.exit_time !== null && t.exit_time <= frame.time
    );
    if (closedTrades.length > 0) {
      const last = closedTrades[closedTrades.length - 1];
      html += '<h3>Last Trade</h3>';
      const cls = last.result === 'win' ? 'bull' : last.result === 'loss' ? 'bear' : 'neutral';
      html += '<div class="row"><span class="label">Result</span><span class="value ' + cls + '">' +
              (last.result || 'open').toUpperCase() + '</span></div>';
      html += '<div class="row"><span class="label">P&amp;L</span>' +
              '<span class="value ' + cls + '">' +
              (last.pnl >= 0 ? '+' : '') + last.pnl.toFixed(2) +
              '</span></div>';
    }
  }

  panel.innerHTML = html;
}

// --- Evidence panel ---
function updateEvidence(frameIdx) {
  const panel = document.getElementById('evidence-content');
  if (frameIdx >= FRAMES.length) { panel.innerHTML = 'No evidence.'; return; }
  const frame = FRAMES[frameIdx];
  if (!frame.evidence || frame.evidence.length === 0) {
    panel.innerHTML = 'No evidence for this frame.';
    return;
  }
  panel.innerHTML = frame.evidence.map(e => {
    const cls = 'ev-' + e.level;
    const src = e.source ? ' <span class="ev-source">(' + e.source + ')</span>' : '';
    return '<div class="ev-entry ' + cls + '">' + e.text + src + '</div>';
  }).join('');
}

// --- Summary bar ---
function updateSummary(frameIdx) {
  let bal = INITIAL_BALANCE;
  let wins = 0, losses = 0, breakevens = 0, pnl = 0;
  let grossProfit = 0, grossLoss = 0;
  let peak = INITIAL_BALANCE, worst = 0;
  TRADES.forEach(t => {
    if (t.exit_time !== null && t.exit_time <= FRAMES[frameIdx].time && t.pnl !== null) {
      bal += t.pnl;
      pnl += t.pnl;
      if (t.result === 'win') { wins++; grossProfit += t.pnl; }
      else if (t.result === 'loss') { losses++; grossLoss += Math.abs(t.pnl); }
      else if (t.result === 'breakeven') { breakevens++; }
    }
    if (bal > peak) peak = bal;
    const dd = peak > 0 ? (peak - bal) / peak : 0;
    if (dd > worst) worst = dd;
  });
  document.getElementById('s-balance').textContent = bal.toFixed(2);
  const pnlEl = document.getElementById('s-pnl');
  pnlEl.textContent = (pnl >= 0 ? '+' : '') + pnl.toFixed(2);
  pnlEl.className = pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
  const retEl = document.getElementById('s-return');
  const retPct = INITIAL_BALANCE > 0 ? (pnl / INITIAL_BALANCE * 100) : 0;
  retEl.textContent = retPct.toFixed(1) + '%';
  retEl.className = retPct >= 0 ? 'pnl-pos' : 'pnl-neg';
  const totalClosed = wins + losses + breakevens;
  document.getElementById('s-trades').textContent = String(totalClosed);
  document.getElementById('s-breakevens').textContent = String(breakevens);
  const winLossTotal = wins + losses;
  document.getElementById('s-winrate').textContent =
      winLossTotal > 0 ? (wins / winLossTotal * 100).toFixed(0) + '%' : '0.0%';
  const pf = grossLoss > 0 ? (grossProfit / grossLoss) : (grossProfit > 0 ? Infinity : 0);
  document.getElementById('s-pf').textContent =
      pf === Infinity ? '\u221e' : pf.toFixed(2);
  document.getElementById('s-avgwin').textContent =
      wins > 0 ? (grossProfit / wins).toFixed(2) : '0.00';
  document.getElementById('s-avgloss').textContent =
      losses > 0 ? (-grossLoss / losses).toFixed(2) : '0.00';
  const exp = winLossTotal > 0 ? pnl / winLossTotal : 0;
  document.getElementById('s-expectancy').textContent = (exp >= 0 ? '$' : '-$') + Math.abs(exp).toFixed(2);
  document.getElementById('s-drawdown').textContent = (worst * 100).toFixed(1) + '%';
}

// --- Trade timeline ---
function buildTimeline() {
  const bar = document.getElementById('timeline-bar');
  if (CANDLES.length === 0) { bar.innerHTML = ''; return; }
  const minTime = CANDLES[0].time;
  const maxTime = CANDLES[CANDLES.length - 1].time;
  const span = maxTime - minTime || 1;
  let html = '';
  TRADES.forEach((t, i) => {
    const startPct = ((t.entry_time - minTime) / span * 100).toFixed(2);
    const endPct = t.exit_time !== null
      ? ((t.exit_time - minTime) / span * 100).toFixed(2)
      : '100';
    const width = Math.max(parseFloat(endPct) - parseFloat(startPct), 0.3);
    const cls = t.result === 'win' ? 'tl-win' :
                t.result === 'loss' ? 'tl-loss' :
                t.result === 'breakeven' ? 'tl-breakeven' : 'tl-open';
    html += '<div class="timeline-trade ' + cls + '" style="left:' + startPct +
            '%;width:' + width + '%" title="Trade ' + (i+1) + ': ' +
            (t.result || 'open') + ' PnL: ' + (t.pnl !== null ? t.pnl.toFixed(2) : 'open') +
            '"></div>';
  });
  html += '<div class="timeline-cursor" id="timeline-cursor" style="left:0%"></div>';
  bar.innerHTML = html;
}
function updateTimelineCursor(frameIdx) {
  const cursor = document.getElementById('timeline-cursor');
  if (!cursor || CANDLES.length === 0) return;
  if (frameIdx >= FRAMES.length) return;
  const minTime = CANDLES[0].time;
  const maxTime = CANDLES[CANDLES.length - 1].time;
  const span = maxTime - minTime || 1;
  const pct = ((FRAMES[frameIdx].time - minTime) / span * 100).toFixed(2);
  cursor.style.left = pct + '%';
}

// --- Future candle visibility ---
function updateCandles(frameIdx) {
  if (futureVisibility === 'hide') {
    const cutoff = FRAMES[frameIdx].time;
    const visible = CANDLES.filter(c => c.time <= cutoff);
    candleSeries.setData(visible);
  } else if (futureVisibility === 'dim') {
    const cutoff = FRAMES[frameIdx].time;
    const dimmed = CANDLES.map(c => {
      if (c.time > cutoff) {
        return { time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, color: 'rgba(128,128,128,0.3)', borderColor: 'rgba(128,128,128,0.3)', wickColor: 'rgba(128,128,128,0.3)' };
      }
      return c;
    });
    candleSeries.setData(dimmed);
  } else {
    candleSeries.setData(CANDLES);
  }
}

const futureVisibilityLabels = { hide: '\u{1F441} Hide', dim: '\u{1F441}\uFE0F Dim', show: '\u{1F441}\u200D\u{1F5E1} Show' };
function toggleFutureVisibility() {
  futureVisibility = futureVisibility === 'hide' ? 'dim' : futureVisibility === 'dim' ? 'show' : 'hide';
  document.getElementById('btn-visibility').innerHTML = futureVisibilityLabels[futureVisibility];
  updateCandles(currentFrame);
}

// --- Volume histogram ---
function updateVolume(frameIdx) {
  const cutoff = FRAMES[frameIdx].time;
  if (futureVisibility === 'hide') {
    const visible = CANDLES.filter(c => c.time <= cutoff).map(c => ({
      time: c.time, value: c.volume,
      color: c.close >= c.open ? 'rgba(34,197,94,0.5)' : 'rgba(239,68,68,0.5)',
    }));
    volumeSeries.setData(visible);
  } else if (futureVisibility === 'dim') {
    const data = CANDLES.map(c => {
      if (c.time > cutoff) {
        return { time: c.time, value: c.volume, color: 'rgba(128,128,128,0.2)' };
      }
      return { time: c.time, value: c.volume,
        color: c.close >= c.open ? 'rgba(34,197,94,0.5)' : 'rgba(239,68,68,0.5)' };
    });
    volumeSeries.setData(data);
  } else {
    const data = CANDLES.map(c => ({
      time: c.time, value: c.volume,
      color: c.close >= c.open ? 'rgba(34,197,94,0.5)' : 'rgba(239,68,68,0.5)',
    }));
    volumeSeries.setData(data);
  }
}

// --- Auto-scroll ---
function scrollToFrame(idx) {
  if (idx < 0 || idx >= FRAMES.length) return;
  const time = FRAMES[idx].time;
  programmaticScroll = true;
  const range = chart.timeScale().getVisibleLogicalRange();
  if (!range) { chart.timeScale().scrollToTime(time); return; }
  const seriesData = candleSeries.data();
  const seriesIdx = seriesData.findIndex(d => d.time === time);
  if (seriesIdx < 0) { chart.timeScale().scrollToTime(time); return; }
  const visibleBars = range.to - range.from;
  const currentCenter = (range.from + range.to) / 2;
  const diff = currentCenter - seriesIdx;
  if (Math.abs(diff) < Math.max(2, visibleBars * 0.15)) return;
  const distFromRight = seriesData.length - 1 - seriesIdx;
  const targetPos = Math.max(0, distFromRight - visibleBars / 2);
  chart.timeScale().scrollToPosition(targetPos, {
    animation: { duration: 200, type: 'ease-out' },
  });
}

// --- Frame stepping ---
function updateFrame(idx) {
  if (idx < 0) idx = 0;
  if (idx >= FRAMES.length) idx = FRAMES.length - 1;
  currentFrame = idx;

  // Update EMA series (truncate to current frame)
  Object.entries(EMA_SERIES).forEach(([name, data]) => {
    const cutoff = FRAMES[idx].time;
    const sliced = data.filter(d => d.time <= cutoff);
    if (emaSeriesMap[name]) emaSeriesMap[name].setData(sliced);
  });

  // Update ATR
  const cutoff = FRAMES[idx].time;
  const atrSliced = ATR_DATA.filter(d => d.time <= cutoff);
  atrLine.setData(atrSliced);

  // Update candle visibility (hide/dim future candles)
  updateCandles(idx);
  updateCandleHighlight(idx);
  updateVolume(idx);

  // Update S/R, trades, markers, zigzag
  updateSR(idx);
  updateTradeLines(idx);
  updateMarkers(idx);
  updateZigzag(idx);
  updateInfoPanel(idx);
  updateEvidence(idx);
  updateSummary(idx);
  updateTimelineCursor(idx);

  // Update frame counter
  document.getElementById('frame-num').textContent = String(idx + 1);

  // Snap crosshair to current candle
  const currentCandle = CANDLES.find(c => c.time === FRAMES[idx].time);
  if (currentCandle) {
    chart.setCrosshairPosition(currentCandle.close, currentCandle.time, candleSeries);
  }

  // Auto-scroll chart to current frame
  if (!autoScrollDisabled) {
    scrollToFrame(idx);
  }
}

// --- Controls ---
document.getElementById('btn-first').addEventListener('click', () => {
  stopPlay();
  autoScrollDisabled = false;
  document.getElementById('btn-autoscroll').classList.add('active');
  updateFrame(0);
});
document.getElementById('btn-last').addEventListener('click', () => {
  stopPlay();
  autoScrollDisabled = false;
  document.getElementById('btn-autoscroll').classList.add('active');
  updateFrame(FRAMES.length - 1);
});
document.getElementById('btn-prev').addEventListener('click', () => {
  stopPlay();
  autoScrollDisabled = false;
  document.getElementById('btn-autoscroll').classList.add('active');
  updateFrame(currentFrame - 1);
});
document.getElementById('btn-next').addEventListener('click', () => {
  stopPlay();
  autoScrollDisabled = false;
  document.getElementById('btn-autoscroll').classList.add('active');
  updateFrame(currentFrame + 1);
});
document.getElementById('btn-play').addEventListener('click', togglePlay);
document.getElementById('speed-select').addEventListener('change', () => {
  if (playing) { stopPlay(); startPlay(); }
});
document.getElementById('btn-visibility').addEventListener('click', toggleFutureVisibility);

// Auto-scroll toggle
document.getElementById('btn-autoscroll').addEventListener('click', () => {
  autoScrollDisabled = !autoScrollDisabled;
  const btn = document.getElementById('btn-autoscroll');
  btn.classList.toggle('active', !autoScrollDisabled);
  if (!autoScrollDisabled) scrollToFrame(currentFrame);
});

function togglePlay() {
  if (playing) { stopPlay(); } else { startPlay(); }
}
function startPlay() {
  playing = true;
  autoScrollDisabled = false;
  document.getElementById('btn-autoscroll').classList.add('active');
  document.getElementById('btn-play').textContent = '\u23F8 Pause';
  document.getElementById('btn-play').classList.add('active');
  const speed = parseInt(document.getElementById('speed-select').value, 10);
  playInterval = setInterval(() => {
    if (currentFrame >= FRAMES.length - 1) { stopPlay(); return; }
    updateFrame(currentFrame + 1);
  }, speed);
}
function stopPlay() {
  playing = false;
  document.getElementById('btn-play').textContent = '\u25B6 Play';
  document.getElementById('btn-play').classList.remove('active');
  if (playInterval) { clearInterval(playInterval); playInterval = null; }
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.key === 'Home') { stopPlay(); updateFrame(0); }
  else if (e.key === 'End') { stopPlay(); updateFrame(FRAMES.length - 1); }
  else if (e.key === 'ArrowLeft') { stopPlay(); updateFrame(currentFrame - 1); }
  else if (e.key === 'ArrowRight') { stopPlay(); updateFrame(currentFrame + 1); }
  else if (e.key === ' ') { e.preventDefault(); togglePlay(); }
  else if (e.key === 'v' || e.key === 'V') { toggleFutureVisibility(); }
  else if (e.key === 'a' || e.key === 'A') {
    autoScrollDisabled = !autoScrollDisabled;
    document.getElementById('btn-autoscroll').classList.toggle('active', !autoScrollDisabled);
    if (!autoScrollDisabled) scrollToFrame(currentFrame);
  }
});

// Disable auto-scroll on user interaction (manual pan/zoom)
chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
  if (programmaticScroll) { programmaticScroll = false; return; }
  if (!playing) {
    autoScrollDisabled = true;
    document.getElementById('btn-autoscroll').classList.remove('active');
  }
});
chartContainer.addEventListener('mousedown', () => {
  if (!playing) { autoScrollDisabled = true; document.getElementById('btn-autoscroll').classList.remove('active'); }
});
chartContainer.addEventListener('wheel', () => {
  if (!playing) { autoScrollDisabled = true; document.getElementById('btn-autoscroll').classList.remove('active'); }
});
chartContainer.addEventListener('touchstart', () => {
  if (!playing) { autoScrollDisabled = true; document.getElementById('btn-autoscroll').classList.remove('active'); }
});

// --- Resize ---
window.addEventListener('resize', () => {
  chart.applyOptions({ width: chartContainer.clientWidth });
  atrChart.applyOptions({ width: atrContainer.clientWidth });
  volumeChart.applyOptions({ width: volumeContainer.clientWidth });
});

// --- Init ---
document.getElementById('frame-total').textContent = String(FRAMES.length);
buildTimeline();
if (FRAMES.length > 0) {
  updateFrame(0);
} else {
  document.getElementById('info-content').innerHTML = 'No frames to display.';
  document.getElementById('evidence-content').innerHTML = 'No evidence.';
}
