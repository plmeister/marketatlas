'use strict';

const assert = require('assert');
const { installBrowserMocks, resetBrowserMocks, createEl } = require('./mock_helpers.js');
const { makeModel, EMA_SERIES, ATR_DATA, FRAMES } = require('./sample_data.js');
const {
  ChartView, InfoPanelView, EvidencePanelView, SummaryBarView, TimelineBarView,
} = require('../../src/marketatlas/visualization/base/views.js');

installBrowserMocks();

let passed = 0;
let failed = 0;

function test(name, fn) {
  resetBrowserMocks();
  try {
    fn();
    passed++;
    console.log(`  \u2713 ${name}`);
  } catch (e) {
    failed++;
    console.log(`  \u2716 ${name}`);
    console.log(`    ${e.message}`);
  }
}

function makeContainers() {
  return {
    main: createEl('chart-container'),
    atr: createEl('atr-container'),
    volume: createEl('volume-container'),
  };
}

console.log('\nChartView Timeframe Annotation Tests\n');

// --- build(): annotation series only on primary TF ---
test('build on primary TF creates EMA and zigzag annotation series', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  assert.deepStrictEqual(Object.keys(cv.emaSeriesMap).sort(), Object.keys(EMA_SERIES).sort());
  assert.ok(cv.zigzagBull, 'zigzagBull series should exist');
  assert.ok(cv.zigzagBear, 'zigzagBear series should exist');
  assert.strictEqual(cv.atrSeries.data.length, ATR_DATA.length);
});

test('build on secondary TF skips EMA/zigzag annotations and clears ATR', () => {
  const model = makeModel();
  model.switchTF('1w');
  const cv = new ChartView(model, makeContainers());
  cv.build('1w');
  assert.strictEqual(Object.keys(cv.emaSeriesMap).length, 0);
  assert.strictEqual(cv.zigzagBull, null);
  assert.strictEqual(cv.zigzagBear, null);
  assert.strictEqual(cv.atrSeries.data.length, 0);
});

test('rebuild after TF switch destroys old charts and restores annotations', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  const charts = global.LightweightCharts.createdCharts;
  cv.build('1d');
  assert.strictEqual(charts.length, 3);
  model.switchTF('1w');
  cv.build('1w');
  assert.strictEqual(charts.length, 6);
  assert.ok(charts[0].removed, 'previous main chart removed');
  assert.ok(charts[1].removed, 'previous atr chart removed');
  assert.ok(charts[2].removed, 'previous volume chart removed');
  assert.strictEqual(Object.keys(cv.emaSeriesMap).length, 0);
  model.switchTF('1d');
  cv.build('1d');
  assert.ok(Object.keys(cv.emaSeriesMap).length > 0, 'annotations restored on primary TF');
});

// --- updateEMAs() ---
test('updateEMAs truncates EMA data to frame time on primary TF', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateEMAs(3); // frame time 2024-01-05
  assert.strictEqual(cv.emaSeriesMap.EMA10.data.length, 5);
});

test('updateEMAs is a no-op on secondary TF', () => {
  const model = makeModel();
  model.switchTF('1w');
  const cv = new ChartView(model, makeContainers());
  cv.build('1w');
  cv.updateEMAs(3);
  assert.strictEqual(Object.keys(cv.emaSeriesMap).length, 0);
});

// --- updateATR() ---
test('updateATR truncates ATR data on primary TF', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateATR(3);
  assert.strictEqual(cv.atrSeries.data.length, 5);
});

test('updateATR keeps ATR panel empty on secondary TF', () => {
  const model = makeModel();
  model.switchTF('1w');
  const cv = new ChartView(model, makeContainers());
  cv.build('1w');
  cv.updateATR(3);
  assert.strictEqual(cv.atrSeries.data.length, 0);
});

// --- updateSR() ---
test('updateSR adds price lines for levels meeting minTouches on primary TF', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateSR(1);
  assert.strictEqual(cv.srPriceLines.length, 1);
  assert.strictEqual(cv.srPriceLines[0].price, 100);
});

test('updateSR skips levels below minTouches', () => {
  const model = makeModel({ MIN_TOUCHES: 4 });
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateSR(4); // strongest levels have strength 3 < 4
  assert.strictEqual(cv.srPriceLines.length, 0);
});

test('updateSR is a no-op on secondary TF', () => {
  const model = makeModel();
  model.switchTF('1w');
  const cv = new ChartView(model, makeContainers());
  cv.build('1w');
  cv.updateSR(1);
  assert.strictEqual(cv.srPriceLines.length, 0);
});

// --- updateZigzag() ---
test('updateZigzag draws bullish pullback pattern on primary TF', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateZigzag(2); // frame 2 has detected bullish pullback
  assert.strictEqual(cv.zigzagBull.data.length, 3);
  assert.strictEqual(cv.zigzagBull.opts.lineVisible, true);
  assert.strictEqual(cv.zigzagBear.opts.lineVisible, false);
});

test('updateZigzag hides lines when no pullback present', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateZigzag(5); // frame 5 has no pullback fact
  assert.strictEqual(cv.zigzagBull.opts.lineVisible, false);
  assert.strictEqual(cv.zigzagBear.opts.lineVisible, false);
});

test('updateZigzag is a no-op on secondary TF', () => {
  const model = makeModel();
  model.switchTF('1w');
  const cv = new ChartView(model, makeContainers());
  cv.build('1w');
  cv.updateZigzag(2);
  assert.strictEqual(cv.zigzagBull, null);
  assert.strictEqual(cv.zigzagBear, null);
});

// --- updateTrades(): trades shown on ALL timeframes ---
test('updateTrades shows trade lines on secondary TF (not TF-gated)', () => {
  const model = makeModel();
  model.switchTF('1w');
  const cv = new ChartView(model, makeContainers());
  cv.build('1w');
  cv.updateTrades(3); // frame time 2024-01-05, trade 2 active
  assert.strictEqual(cv.tradePriceLines.length, 3); // entry + stop + target
});

test('updateTrades shows SR and trade lines together on primary TF', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateTrades(3);
  assert.strictEqual(cv.srPriceLines.length, 2);
  assert.strictEqual(cv.tradePriceLines.length, 3);
});

// --- updateCandles(): future candle visibility modes ---
test('updateCandles hides future candles in hide mode', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateCandles(3); // frame time 2024-01-05 -> 5 candles visible
  assert.strictEqual(cv.candleSeries.data.length, 5);
});

test('updateCandles dims future candles in dim mode', () => {
  const model = makeModel();
  model.futureVisibility = 'dim';
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateCandles(3);
  assert.strictEqual(cv.candleSeries.data.length, 10);
  const future = cv.candleSeries.data.slice(5);
  assert.strictEqual(future.length, 5);
  assert.ok(future.every(c => c.color === 'rgba(128,128,128,0.3)'));
});

// --- updateMarkers() ---
test('updateMarkers includes current candle, pullback and trade markers', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateMarkers(2);
  const markers = cv.candleSeries.markers;
  assert.ok(markers.length >= 3);
  const shapes = markers.map(m => m.shape);
  assert.ok(shapes.includes('diamond'), 'current candle diamond marker');
  assert.ok(shapes.includes('arrowUp'), 'pullback marker');
});

test('updateMarkers sorts markers chronologically', () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build('1d');
  cv.updateMarkers(7);
  const times = cv.candleSeries.markers.map(m => Date.parse(m.time));
  for (let i = 1; i < times.length; i++) {
    assert.ok(times[i] >= times[i - 1], `markers out of order at ${i}`);
  }
});

console.log('\nInfoPanelView Tests\n');

test('info shows frame header and date', () => {
  const model = makeModel();
  const ip = new InfoPanelView('info-content');
  ip.update(model, 0);
  const html = document.getElementById('info-content').innerHTML;
  assert.ok(html.includes('Frame 1/6'));
  assert.ok(html.includes('2024-01-01'));
});

test('info shows balance including closed PnL', () => {
  const model = makeModel();
  const ip = new InfoPanelView('info-content');
  ip.update(model, 3); // trade 1 closed +300
  const html = document.getElementById('info-content').innerHTML;
  assert.ok(html.includes('10300.00'));
});

test('info shows trend indicator', () => {
  const model = makeModel();
  const ip = new InfoPanelView('info-content');
  ip.update(model, 3); // TREND fact bullish
  const html = document.getElementById('info-content').innerHTML;
  assert.ok(html.includes('BULLISH'));
});

test('info shows open trade details', () => {
  const model = makeModel();
  const ip = new InfoPanelView('info-content');
  ip.update(model, 5); // frame time 2024-01-10, trade 3 still open
  const html = document.getElementById('info-content').innerHTML;
  assert.ok(html.includes('OPEN LONG'));
  assert.ok(html.includes('120.00'));
});

test('info shows no data on empty model', () => {
  const { AppModel } = require('../../src/marketatlas/visualization/base/models.js');
  const model = new AppModel({});
  const ip = new InfoPanelView('info-content');
  ip.update(model, 0);
  assert.ok(document.getElementById('info-content').innerHTML.includes('No data.'));
});

console.log('\nEvidencePanelView Tests\n');

test('evidence renders entries with level class and source', () => {
  const model = makeModel();
  const ep = new EvidencePanelView('evidence-content');
  ep.update(model, 0);
  const html = document.getElementById('evidence-content').innerHTML;
  assert.ok(html.includes('Trend up'));
  assert.ok(html.includes('ev-info'));
  assert.ok(html.includes('(test)'));
});

test('evidence shows empty message when no evidence', () => {
  const model = makeModel();
  const ep = new EvidencePanelView('evidence-content');
  ep.update(model, 1);
  assert.ok(document.getElementById('evidence-content').innerHTML.includes('No evidence for this frame.'));
});

console.log('\nSummaryBarView Tests\n');

test('summary populates stats from computeSummary', () => {
  const model = makeModel();
  const sb = new SummaryBarView();
  sb.update(model, 3);
  assert.strictEqual(document.getElementById('s-balance').textContent, '10300.00');
  assert.strictEqual(document.getElementById('s-pnl').textContent, '+300.00');
  assert.strictEqual(document.getElementById('s-return').textContent, '3.0%');
  assert.strictEqual(document.getElementById('s-trades').textContent, '1');
  assert.strictEqual(document.getElementById('s-winrate').textContent, '100%');
});

console.log('\nTimelineBarView Tests\n');

test('timeline builds trade bars and cursor', () => {
  const model = makeModel();
  const tb = new TimelineBarView('timeline-bar');
  tb.build(model);
  const html = document.getElementById('timeline-bar').innerHTML;
  assert.ok(html.includes('timeline-trade'));
  assert.ok(html.includes('timeline-cursor'));
});

test('timeline cursor moves to frame time', () => {
  const model = makeModel();
  const tb = new TimelineBarView('timeline-bar');
  tb.build(model);
  tb.updateCursor(model, 4);
  const cursor = document.getElementById('timeline-cursor');
  assert.ok(cursor.style.left.endsWith('%'));
  assert.ok(parseFloat(cursor.style.left) > 0);
});

console.log(`\n${passed} passed, ${failed} failed, ${passed + failed} total\n`);
process.exit(failed > 0 ? 1 : 0);
