"use strict";

const assert = require("assert");
const { installBrowserMocks, resetBrowserMocks, createEl } = require("./mock_helpers.js");
const { makeModel, EMA_SERIES, ATR_DATA } = require("./sample_data.js");
const {
  ChartView,
  InfoPanelView,
  EvidencePanelView,
  SummaryBarView,
  TimelineBarView,
} = require("../../src/marketatlas/visualization/base/views.js");

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
    main: createEl("chart-container"),
    atr: createEl("atr-container"),
    volume: createEl("volume-container"),
  };
}

console.log("\nChartView Timeframe Annotation Tests\n");

// --- build(): annotation series only on primary TF ---
test("build on primary TF creates EMA and zigzag annotation series", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  assert.deepStrictEqual(Object.keys(cv.emaSeriesMap).sort(), Object.keys(EMA_SERIES).sort());
  assert.ok(cv.zigzagBull, "zigzagBull series should exist");
  assert.ok(cv.zigzagBear, "zigzagBear series should exist");
  assert.strictEqual(cv.atrSeries.data().length, ATR_DATA.length);
});

test("build on secondary TF skips EMA/zigzag annotations and clears ATR", () => {
  const model = makeModel();
  model.switchTF("1w");
  const cv = new ChartView(model, makeContainers());
  cv.build("1w");
  assert.strictEqual(Object.keys(cv.emaSeriesMap).length, 0);
  assert.strictEqual(cv.zigzagBull, null);
  assert.strictEqual(cv.zigzagBear, null);
  assert.strictEqual(cv.atrSeries.data().length, 0);
});

test("rebuild after TF switch destroys old charts and restores annotations", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  const charts = global.LightweightCharts.createdCharts;
  cv.build("1d");
  assert.strictEqual(charts.length, 3);
  model.switchTF("1w");
  cv.build("1w");
  assert.strictEqual(charts.length, 6);
  assert.ok(charts[0].removed, "previous main chart removed");
  assert.ok(charts[1].removed, "previous atr chart removed");
  assert.ok(charts[2].removed, "previous volume chart removed");
  assert.strictEqual(Object.keys(cv.emaSeriesMap).length, 0);
  model.switchTF("1d");
  cv.build("1d");
  assert.ok(Object.keys(cv.emaSeriesMap).length > 0, "annotations restored on primary TF");
});

// --- updateEMAs() ---
test("updateEMAs truncates EMA data to frame time on primary TF", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateEMAs(3); // frame time 2024-01-05
  assert.strictEqual(cv.emaSeriesMap.EMA10.data().length, 5);
});

test("updateEMAs is a no-op on secondary TF", () => {
  const model = makeModel();
  model.switchTF("1w");
  const cv = new ChartView(model, makeContainers());
  cv.build("1w");
  cv.updateEMAs(3);
  assert.strictEqual(Object.keys(cv.emaSeriesMap).length, 0);
});

// --- updateATR() ---
test("updateATR truncates ATR data on primary TF", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateATR(3);
  assert.strictEqual(cv.atrSeries.data().length, 5);
});

test("updateATR keeps ATR panel empty on secondary TF", () => {
  const model = makeModel();
  model.switchTF("1w");
  const cv = new ChartView(model, makeContainers());
  cv.build("1w");
  cv.updateATR(3);
  assert.strictEqual(cv.atrSeries.data().length, 0);
});

// --- updateSR() ---
test("updateSR adds price lines for levels meeting minTouches on primary TF", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateSR(1);
  assert.strictEqual(cv.srPriceLines.length, 1);
  assert.strictEqual(cv.srPriceLines[0].price, 100);
});

test("updateSR skips levels below minTouches", () => {
  const model = makeModel({ MIN_TOUCHES: 4 });
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateSR(4); // strongest levels have strength 3 < 4
  assert.strictEqual(cv.srPriceLines.length, 0);
});

test("updateSR shows SR price lines on secondary TF", () => {
  const model = makeModel();
  model.switchTF("1w");
  const cv = new ChartView(model, makeContainers());
  cv.build("1w");
  cv.updateSR(1);
  assert.strictEqual(cv.srPriceLines.length, 1);
});

test("updateSR replaces previous frame lines instead of stacking", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateSR(1); // 1 level
  assert.strictEqual(cv.srPriceLines.length, 1);
  assert.strictEqual(cv.candleSeries.priceLines.length, 1);
  cv.updateSR(2); // still 1 level — old line must be detached, not added to
  assert.strictEqual(cv.srPriceLines.length, 1);
  assert.strictEqual(cv.candleSeries.priceLines.length, 1);
  cv.updateSR(3); // 2 levels
  assert.strictEqual(cv.srPriceLines.length, 2);
  assert.strictEqual(cv.candleSeries.priceLines.length, 2);
});

// --- updateZigzag() ---
test("updateZigzag draws bullish swing-structure zigzag on primary TF", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateZigzag(2); // frame 2 has a bullish swingstructure fact
  assert.strictEqual(cv.zigzagBull.data().length, 3);
  assert.strictEqual(cv.zigzagBull.opts.lineVisible, true);
  assert.strictEqual(cv.zigzagBear.opts.lineVisible, false);
});

test("updateZigzag hides lines when no swingstructure present", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateZigzag(5); // frame 5 has no swingstructure fact
  assert.strictEqual(cv.zigzagBull.opts.lineVisible, false);
  assert.strictEqual(cv.zigzagBear.opts.lineVisible, false);
});

test("updateZigzag is a no-op on secondary TF", () => {
  const model = makeModel();
  model.switchTF("1w");
  const cv = new ChartView(model, makeContainers());
  cv.build("1w");
  cv.updateZigzag(2);
  assert.strictEqual(cv.zigzagBull, null);
  assert.strictEqual(cv.zigzagBear, null);
});

// --- updateTrades(): trades shown on ALL timeframes ---
test("updateTrades builds trade boxes on secondary TF (not TF-gated)", () => {
  const model = makeModel();
  model.switchTF("1w");
  const cv = new ChartView(model, makeContainers());
  cv.build("1w");
  cv.updateTrades(3); // frame time 2024-01-05, trades 1+2 placed
  assert.strictEqual(cv.tradeBoxes.length, 2);
});

test("updateTrades shows SR and trade boxes together on primary TF", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(3);
  assert.strictEqual(cv.srPriceLines.length, 2);
  assert.strictEqual(cv.tradeBoxes.length, 2);
});

test("updateTrades excludes trades not yet placed at the frame time", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(0); // frame time 2024-01-01, no trades placed yet
  assert.deepStrictEqual(cv.tradeBoxes, []);
});

test("trade box spans entry to entry+maxHold clamped to last candle", () => {
  const model = makeModel({ MAX_HOLD_DAYS: 5 });
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(4); // frame time 2024-01-08, trades 1,2,3 placed
  const t3 = cv.tradeBoxes.find((b) => b.fromTime === "2024-01-08");
  assert.deepStrictEqual(t3, {
    fromTime: "2024-01-08",
    toTime: "2024-01-10",
    entry: 120,
    stop: 115,
    target: 135,
  });
});

test("hide mode clamps trade box end to the current frame (grows from entry)", () => {
  const model = makeModel(); // futureVisibility defaults to "hide"
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(3); // frame time 2024-01-05
  const t1 = cv.tradeBoxes.find((b) => b.fromTime === "2024-01-02");
  assert.strictEqual(t1.toTime, "2024-01-05"); // clamped, not entry+maxHold
  const t2 = cv.tradeBoxes.find((b) => b.fromTime === "2024-01-05");
  assert.ok(t2, "trade entered on the current frame still draws a box");
  assert.strictEqual(t2.toTime, "2024-01-08"); // widened to the next frame
});

test("show mode keeps the full trade box span from entry", () => {
  const model = makeModel({ MAX_HOLD_DAYS: 5 });
  model.futureVisibility = "show";
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(4); // frame time 2024-01-08
  const t3 = cv.tradeBoxes.find((b) => b.fromTime === "2024-01-08");
  assert.strictEqual(t3.toTime, "2024-01-10"); // full entry+maxHold span
});

test("trade box primitive attaches and detaches on rebuild", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  const firstPrim = cv.tradeBoxPrimitive;
  const firstCandles = cv.candleSeries;
  assert.ok(firstPrim, "primitive created");
  assert.strictEqual(firstCandles.primitives.length, 1);
  const charts = global.LightweightCharts.createdCharts;
  cv.build("1d"); // rebuild detaches from old series, attaches to new
  assert.strictEqual(charts[0].removed, true);
  assert.strictEqual(firstCandles.primitives.length, 0);
  assert.notStrictEqual(cv.tradeBoxPrimitive, firstPrim);
  assert.strictEqual(cv.candleSeries.primitives.length, 1);
});

test("scrollToFrame re-anchors when candle data shrank (stepping back)", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.scrollToFrame(5); // frame 2024-01-10, all 10 candles visible
  const chart = global.LightweightCharts.createdCharts[0];
  const calls = chart.visibleLogicalRanges;
  assert.ok(calls.length >= 1);
  // Step back with future candles hidden: series shrinks to 1 candle, the
  // previous logical range is stale — must re-anchor at index 0.
  cv.updateCandles(0);
  cv.scrollToFrame(0);
  const last = calls[calls.length - 1];
  assert.strictEqual(last.from, 0);
  assert.ok(last.to > last.from);
});

// --- trade box hover tooltip ---
test("trade tooltip appears on hover over a trade box and hides on leave", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(5); // frame 2024-01-10, all trades placed
  const chart = global.LightweightCharts.createdCharts[0];
  // trade 2 box spans x [40,90], y [110,130] in mock coordinates
  chart.crosshairHandlers[0]({ point: { x: 60, y: 118 } });
  const tooltip = cv._tooltipEl;
  assert.ok(tooltip, "tooltip element created");
  assert.notStrictEqual(tooltip.style.display, "none");
  assert.ok(tooltip.innerHTML.includes("115"), "entry in tooltip");
  assert.ok(tooltip.innerHTML.includes("130"), "target in tooltip");
  assert.ok(tooltip.innerHTML.includes("LOSS"), "resolved result in tooltip");
  chart.crosshairHandlers[0]({ point: null });
  assert.strictEqual(tooltip.style.display, "none");
});

test("trade tooltip hides when hovering off any box", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(5);
  const chart = global.LightweightCharts.createdCharts[0];
  chart.crosshairHandlers[0]({ point: { x: 60, y: 118 } });
  const tooltip = cv._tooltipEl;
  assert.notStrictEqual(tooltip.style.display, "none");
  chart.crosshairHandlers[0]({ point: { x: 5, y: 5 } }); // outside all boxes
  assert.strictEqual(tooltip.style.display, "none");
});

// --- annotation hover tooltips (SR lines, swings, pullbacks, signals) ---
function tooltipHtmlFor(cv, param) {
  const chart = global.LightweightCharts.createdCharts[0];
  chart.crosshairHandlers[0](param);
  const el = cv._tooltipEl;
  assert.ok(el, "tooltip element created");
  return el;
}

test("SR line hover shows support info near the line price", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(5); // frame 2024-01-10, support at 100, resistance 115/125
  const tooltip = tooltipHtmlFor(cv, { time: "2024-01-10", point: { x: 5, y: 102 } });
  assert.notStrictEqual(tooltip.style.display, "none");
  assert.ok(tooltip.innerHTML.includes("SUPPORT"), "support label");
  assert.ok(tooltip.innerHTML.includes("100.00"), "price shown");
  assert.ok(tooltip.innerHTML.includes("3 touches"), "strength shown");
});

test("SR line hover shows resistance info near the line price", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(5);
  const tooltip = tooltipHtmlFor(cv, { time: "2024-01-10", point: { x: 5, y: 116 } });
  assert.ok(tooltip.innerHTML.includes("RESISTANCE"), "resistance label");
  assert.ok(tooltip.innerHTML.includes("115.00"), "price shown");
});

test("SR hover hides when pointer is far from any level", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(5);
  const chart = global.LightweightCharts.createdCharts[0];
  chart.crosshairHandlers[0]({ time: "2024-01-10", point: { x: 5, y: 200 } });
  assert.ok(!cv._tooltipEl || cv._tooltipEl.style.display === "none", "no tooltip shown");
});

test("swing marker hover shows swing high/low details", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(5); // frame 5 carries 1d swings at 2024-01-05 (high 118) / 2024-01-06 (low 109)
  const tooltip = tooltipHtmlFor(cv, { time: "2024-01-05", point: { x: 5, y: 118 } });
  assert.ok(tooltip.innerHTML.includes("SWING HIGH"), "high label");
  assert.ok(tooltip.innerHTML.includes("118.00"), "swing price shown");
  const tooltip2 = tooltipHtmlFor(cv, { time: "2024-01-06", point: { x: 5, y: 109 } });
  assert.ok(tooltip2.innerHTML.includes("SWING LOW"), "low label");
  assert.ok(tooltip2.innerHTML.includes("109.00"), "low price shown");
});

test("swing hover skips swings on other timeframes", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(3); // frame 3 has a 1w swing at 2024-01-06 only
  const chart = global.LightweightCharts.createdCharts[0];
  chart.crosshairHandlers[0]({ time: "2024-01-06", point: { x: 5, y: 90 } });
  assert.ok(!cv._tooltipEl || cv._tooltipEl.style.display === "none", "no tooltip shown");
});

test("pullback marker hover shows direction and swing pattern", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(2); // frame 2 has pullback at 2024-01-03
  const tooltip = tooltipHtmlFor(cv, { time: "2024-01-03", point: { x: 5, y: 108 } });
  assert.ok(tooltip.innerHTML.includes("PULLBACK"), "pullback label");
  assert.ok(tooltip.innerHTML.includes("bullish"), "direction shown");
  assert.ok(tooltip.innerHTML.includes("108"), "swing pattern shown");
});

test("pullback candle popup also shows its signal and rejection", () => {
  const model = makeModel();
  model.frames[2].signals = [{ direction: "bullish", confidence: 0.75, source: "PB" }];
  model.frames[2].signal_rejections = [
    { text: "no valid ATR fact", level: "warning", source: "RiskEngine" },
  ];
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(2); // frame 2 has pullback at 2024-01-03
  const tooltip = tooltipHtmlFor(cv, { time: "2024-01-03", point: { x: 5, y: 108 } });
  assert.ok(tooltip.innerHTML.includes("PULLBACK"), "pullback label");
  assert.ok(tooltip.innerHTML.includes("SIGNAL BULLISH"), "signal label");
  assert.ok(tooltip.innerHTML.includes("REJECTED"), "rejection label");
  assert.ok(tooltip.innerHTML.includes("no valid ATR fact"), "rejection text shown");
});

test("signal hover shows signal and risk-rejection details", () => {
  const model = makeModel();
  model.frames[3].signals = [{ direction: "bullish", confidence: 0.8, source: "PB" }];
  model.frames[3].risk_evidence = [
    { text: "Rejected: rr 0.5 below min 1.0", level: "warning", source: "risk" },
  ];
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(3); // frame 2024-01-05 carries the signal
  const tooltip = tooltipHtmlFor(cv, { time: "2024-01-05", point: { x: 5, y: 112 } });
  assert.ok(tooltip.innerHTML.includes("SIGNAL BULLISH"), "signal label");
  assert.ok(tooltip.innerHTML.includes("0.80"), "confidence shown");
  assert.ok(tooltip.innerHTML.includes("Rejected"), "rejection text shown");
});

test("trade box takes priority over SR line tooltip", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(5);
  const tooltip = tooltipHtmlFor(cv, { time: "2024-01-05", point: { x: 60, y: 118 } });
  // Inside trade 2 box (entry 115/stop 110/target 130) and near SR 115 line.
  assert.ok(tooltip.innerHTML.includes("LOSS"), "trade result wins");
  assert.ok(!tooltip.innerHTML.includes("RESISTANCE"), "SR line suppressed");
});

// --- TradeBoxPrimitive._draw: rectangle rendering via callback API ---
test("trade box primitive draws green reward and red risk rectangles", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateTrades(5); // all trades placed by frame 2024-01-10
  assert.ok(cv.tradeBoxPrimitive, "primitive attached");
  const ops = [];
  const ctx = {
    fillRect(x, y, w, h) {
      ops.push({ x, y, w, h, style: this.fillStyle });
    },
    save() {},
    restore() {},
    setTransform() {},
    scale() {},
  };
  // v4.1.3 useMediaCoordinateSpace is a callback API: invoke with target-like
  // object that calls the callback with { context, mediaSize }.
  const target = {
    useMediaCoordinateSpace(cb) {
      return cb({ context: ctx, mediaSize: { x: 800, y: 500 } });
    },
  };
  const views = cv.tradeBoxPrimitive.paneViews();
  assert.ok(views.length >= 1, "pane views present");
  const renderer = views[0].renderer();
  renderer.draw(target);
  assert.ok(ops.length >= 2, "at least one rectangle per zone");
  assert.ok(
    ops.some((o) => o.style === "#22c55e"),
    "green reward zone drawn",
  );
  assert.ok(
    ops.some((o) => o.style === "#ef4444"),
    "red risk zone drawn",
  );
  for (const o of ops) {
    assert.ok(Number.isFinite(o.x) && Number.isFinite(o.y), "x/y finite");
    assert.ok(o.w > 0 && o.h > 0, "positive width/height");
  }
});
test("updateCandles hides future candles in hide mode", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateCandles(3); // frame time 2024-01-05 -> 5 candles visible
  assert.strictEqual(cv.candleSeries.data().length, 5);
});

test("updateCandles dims future candles in dim mode", () => {
  const model = makeModel();
  model.futureVisibility = "dim";
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateCandles(3);
  assert.strictEqual(cv.candleSeries.data().length, 10);
  const future = cv.candleSeries.data().slice(5);
  assert.strictEqual(future.length, 5);
  assert.ok(future.every((c) => c.color === "rgba(128,128,128,0.3)"));
});

// --- updateMarkers() ---
test("updateMarkers includes current candle, pullback and trade resolution markers", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateMarkers(2); // frame 2024-01-03
  const shapes = cv.candleSeries.markers.map((m) => m.shape);
  assert.ok(shapes.includes("diamond"), "current candle diamond marker");
  assert.ok(shapes.includes("arrowUp"), "pullback marker");
  assert.ok(
    cv.candleSeries.markers.every((m) => m.text !== "EMA"),
    "entry arrow marker should be removed",
  );
  cv.updateMarkers(3); // frame 2024-01-05: trade 1 resolved win on 01-04
  const circles = cv.candleSeries.markers.filter((m) => m.shape === "circle");
  assert.strictEqual(circles.length, 1);
  assert.strictEqual(circles[0].time, "2024-01-04");
  assert.strictEqual(circles[0].color, "#22c55e");
});

test("updateMarkers sorts markers chronologically", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateMarkers(7);
  const times = cv.candleSeries.markers.map((m) => Date.parse(m.time));
  for (let i = 1; i < times.length; i++) {
    assert.ok(times[i] >= times[i - 1], `markers out of order at ${i}`);
  }
});

test("updateMarkers places swing markers at native swing times", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateMarkers(5); // frame 5 has 1d swing facts at 1d indices 4,5
  const swingTimes = cv.candleSeries.markers
    .filter((m) => m.color === "#f59e0b" || m.color === "#3b82f6")
    .map((m) => m.time)
    .sort();
  assert.deepStrictEqual(swingTimes, ["2024-01-05", "2024-01-06"]);
});

test("updateMarkers on 1d view filters out 1w swings", () => {
  const model = makeModel();
  const cv = new ChartView(model, makeContainers());
  cv.build("1d");
  cv.updateMarkers(3); // frame 3 has a 1w swing only
  const swingMarkers = cv.candleSeries.markers.filter(
    (m) => m.color === "#f59e0b" || m.color === "#3b82f6",
  );
  assert.deepStrictEqual(swingMarkers, []);
});

test("updateMarkers on 1w view shows 1w swings and hides 1d swings", () => {
  const model = makeModel();
  model.switchTF("1w");
  const cv = new ChartView(model, makeContainers());
  cv.build("1w");
  cv.updateMarkers(3); // frame 3 has a 1w swing at 1w candle 2024-01-06
  const swingMarkers = cv.candleSeries.markers.filter(
    (m) => m.color === "#f59e0b" || m.color === "#3b82f6",
  );
  assert.deepStrictEqual(swingMarkers.map((m) => m.time).sort(), ["2024-01-06"]);
});

test("updateMarkers on 1w view hides 1d swings from current frame", () => {
  const model = makeModel();
  model.switchTF("1w");
  const cv = new ChartView(model, makeContainers());
  cv.build("1w");
  cv.updateMarkers(5); // frame 5 has 1d swings only
  const swingMarkers = cv.candleSeries.markers.filter(
    (m) => m.color === "#f59e0b" || m.color === "#3b82f6",
  );
  assert.deepStrictEqual(swingMarkers, []);
});

console.log("\nInfoPanelView Tests\n");

test("info shows frame header and date", () => {
  const model = makeModel();
  const ip = new InfoPanelView("info-content");
  ip.update(model, 0);
  const html = document.getElementById("info-content").innerHTML;
  assert.ok(html.includes("Frame 1/6"));
  assert.ok(html.includes("2024-01-01"));
});

test("info shows balance including closed PnL", () => {
  const model = makeModel();
  const ip = new InfoPanelView("info-content");
  ip.update(model, 3); // trade 1 closed +300
  const html = document.getElementById("info-content").innerHTML;
  assert.ok(html.includes("10300.00"));
});

test("info shows trend indicator", () => {
  const model = makeModel();
  const ip = new InfoPanelView("info-content");
  ip.update(model, 3); // TREND fact bullish
  const html = document.getElementById("info-content").innerHTML;
  assert.ok(html.includes("BULLISH"));
});

test("info shows open trade details", () => {
  const model = makeModel();
  const ip = new InfoPanelView("info-content");
  ip.update(model, 5); // frame time 2024-01-10, trade 3 still open
  const html = document.getElementById("info-content").innerHTML;
  assert.ok(html.includes("OPEN LONG"));
  assert.ok(html.includes("120.00"));
});

test("info shows no data on empty model", () => {
  const { AppModel } = require("../../src/marketatlas/visualization/base/models.js");
  const model = new AppModel({});
  const ip = new InfoPanelView("info-content");
  ip.update(model, 0);
  assert.ok(document.getElementById("info-content").innerHTML.includes("No data."));
});

console.log("\nEvidencePanelView Tests\n");

test("evidence renders entries with level class and source", () => {
  const model = makeModel();
  const ep = new EvidencePanelView("evidence-content");
  ep.update(model, 0);
  const html = document.getElementById("evidence-content").innerHTML;
  assert.ok(html.includes("Trend up"));
  assert.ok(html.includes("ev-info"));
  assert.ok(html.includes("(test)"));
});

test("evidence shows empty message when no evidence", () => {
  const model = makeModel();
  const ep = new EvidencePanelView("evidence-content");
  ep.update(model, 1);
  assert.ok(
    document.getElementById("evidence-content").innerHTML.includes("No evidence for this frame."),
  );
});

console.log("\nSummaryBarView Tests\n");

test("summary populates stats from computeSummary", () => {
  const model = makeModel();
  const sb = new SummaryBarView();
  sb.update(model, 3);
  assert.strictEqual(document.getElementById("s-balance").textContent, "10300.00");
  assert.strictEqual(document.getElementById("s-pnl").textContent, "+300.00");
  assert.strictEqual(document.getElementById("s-return").textContent, "3.0%");
  assert.strictEqual(document.getElementById("s-trades").textContent, "1");
  assert.strictEqual(document.getElementById("s-winrate").textContent, "100%");
});

console.log("\nTimelineBarView Tests\n");

test("timeline builds trade bars and cursor", () => {
  const model = makeModel();
  const tb = new TimelineBarView("timeline-bar");
  tb.build(model);
  const html = document.getElementById("timeline-bar").innerHTML;
  assert.ok(html.includes("timeline-trade"));
  assert.ok(html.includes("timeline-cursor"));
});

test("timeline cursor moves to frame time", () => {
  const model = makeModel();
  const tb = new TimelineBarView("timeline-bar");
  tb.build(model);
  tb.updateCursor(model, 4);
  const cursor = document.getElementById("timeline-cursor");
  assert.ok(cursor.style.left.endsWith("%"));
  assert.ok(parseFloat(cursor.style.left) > 0);
});

// --- _pricePrecision ---
test("_pricePrecision uses 6dp for sub-1 instruments", () => {
  const { _pricePrecision } = require("../../src/marketatlas/visualization/base/views/chart.js");
  const m = { candlesByTF: { "1d": [{ low: 0.64698, high: 0.65003 }] } };
  assert.strictEqual(_pricePrecision(m), 6);
});

test("_pricePrecision uses 2dp for large instruments", () => {
  const { _pricePrecision } = require("../../src/marketatlas/visualization/base/views/chart.js");
  const m = { candlesByTF: { "1d": [{ low: 60000, high: 61000 }] } };
  assert.strictEqual(_pricePrecision(m), 2);
});

console.log(`\n${passed} passed, ${failed} failed, ${passed + failed} total\n`);
process.exit(failed > 0 ? 1 : 0);
