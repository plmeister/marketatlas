const assert = require("assert");
const { AppModel, _t, _fmtP } = require("../../src/marketatlas/visualization/base/models.js");

// --- Sample data ---
const CANDLES = [
  { time: "2024-01-01", open: 100, high: 110, low: 99, close: 108, volume: 1000 },
  { time: "2024-01-02", open: 108, high: 115, low: 107, close: 114, volume: 1200 },
  { time: "2024-01-03", open: 114, high: 116, low: 105, close: 106, volume: 900 },
  { time: "2024-01-04", open: 106, high: 112, low: 104, close: 111, volume: 1100 },
  { time: "2024-01-05", open: 111, high: 120, low: 110, close: 118, volume: 1500 },
  { time: "2024-01-06", open: 118, high: 119, low: 108, close: 109, volume: 800 },
  { time: "2024-01-07", open: 109, high: 113, low: 106, close: 112, volume: 950 },
  { time: "2024-01-08", open: 112, high: 125, low: 111, close: 124, volume: 2000 },
  { time: "2024-01-09", open: 124, high: 130, low: 122, close: 128, volume: 1800 },
  { time: "2024-01-10", open: 128, high: 132, low: 125, close: 126, volume: 1600 },
];

const CANDLES_BY_TF = {
  "1d": CANDLES,
  "1w": [
    { time: "2024-01-06", open: 100, high: 120, low: 99, close: 109, volume: 5400 },
    { time: "2024-01-13", open: 109, high: 132, low: 106, close: 126, volume: 6350 },
  ],
};

const FRAMES = [
  { time: "2024-01-01", evidence: [{ text: "Trend up", level: "info", source: "test" }] },
  { time: "2024-01-02", evidence: [] },
  { time: "2024-01-03", evidence: [{ text: "Pullback", level: "warning", source: "pb" }] },
  { time: "2024-01-05", evidence: [] },
  { time: "2024-01-08", evidence: [{ text: "Breakout", level: "signal", source: "test" }] },
  { time: "2024-01-10", evidence: [] },
];

const EMA_SERIES = {
  EMA10: [
    { time: "2024-01-01", value: 102 },
    { time: "2024-01-02", value: 105 },
    { time: "2024-01-03", value: 106 },
    { time: "2024-01-04", value: 107 },
    { time: "2024-01-05", value: 109 },
    { time: "2024-01-06", value: 108 },
    { time: "2024-01-07", value: 109 },
    { time: "2024-01-08", value: 112 },
    { time: "2024-01-09", value: 116 },
    { time: "2024-01-10", value: 118 },
  ],
};

const ATR_DATA = [
  { time: "2024-01-01", value: 3.5 },
  { time: "2024-01-02", value: 3.8 },
  { time: "2024-01-03", value: 4.2 },
  { time: "2024-01-04", value: 3.9 },
  { time: "2024-01-05", value: 4.5 },
  { time: "2024-01-06", value: 4.1 },
  { time: "2024-01-07", value: 3.7 },
  { time: "2024-01-08", value: 5.0 },
  { time: "2024-01-09", value: 5.5 },
  { time: "2024-01-10", value: 5.2 },
];

const SR_DATA = [
  { time: "2024-01-01", levels: [] },
  { time: "2024-01-02", levels: [{ price: 100, strength: 2, type: "support" }] },
  { time: "2024-01-03", levels: [{ price: 100, strength: 3, type: "support" }] },
  {
    time: "2024-01-04",
    levels: [
      { price: 100, strength: 3, type: "support" },
      { price: 115, strength: 2, type: "resistance" },
    ],
  },
  {
    time: "2024-01-05",
    levels: [
      { price: 100, strength: 3, type: "support" },
      { price: 115, strength: 3, type: "resistance" },
    ],
  },
  {
    time: "2024-01-08",
    levels: [
      { price: 100, strength: 3, type: "support" },
      { price: 115, strength: 3, type: "resistance" },
      { price: 125, strength: 2, type: "resistance" },
    ],
  },
  {
    time: "2024-01-10",
    levels: [
      { price: 100, strength: 3, type: "support" },
      { price: 115, strength: 3, type: "resistance" },
      { price: 125, strength: 3, type: "resistance" },
    ],
  },
];

const TRADES = [
  {
    entry_time: "2024-01-02",
    exit_time: "2024-01-04",
    entry: 108,
    stop: 103,
    target: 118,
    direction: "bullish",
    result: "win",
    pnl: 300,
    source: "EMA",
    size: 1.0,
    risk_amount: 50,
    rr_ratio: 3.0,
  },
  {
    entry_time: "2024-01-05",
    exit_time: "2024-01-07",
    entry: 115,
    stop: 110,
    target: 130,
    direction: "bullish",
    result: "loss",
    pnl: -250,
    source: "EMA",
    size: 1.5,
    risk_amount: 75,
    rr_ratio: 2.0,
  },
  {
    entry_time: "2024-01-08",
    exit_time: null,
    entry: 120,
    stop: 115,
    target: 135,
    direction: "bullish",
    result: null,
    pnl: null,
    source: "PB",
    size: 2.0,
    risk_amount: 100,
    rr_ratio: 3.0,
  },
  {
    entry_time: "2024-01-09",
    exit_time: "2024-01-10",
    entry: 125,
    stop: 120,
    target: 140,
    direction: "bullish",
    result: "breakeven",
    pnl: 0,
    source: "PB",
    size: 1.0,
    risk_amount: 50,
    rr_ratio: 3.0,
  },
];

const PULLBACKS = [
  null,
  null,
  {
    time: "2024-01-03",
    position: "belowBar",
    color: "#22c55e",
    shape: "arrowUp",
    text: "Pullback (1.5 ATR)",
  },
  null,
  null,
  null,
  null,
  null,
  null,
  null,
];

const FACTS_DATA = [
  {},
  {},
  {
    PB: {
      type: "pullback",
      status: "detected",
      direction: "bullish",
      retracement_atr: 1.5,
      confirmation_strength: 0.6,
      deviation_pct: 2.1,
      swing_pattern: [108, 114, 106],
      swing_pattern_indices: [1, 2, 3],
    },
  },
  { TREND: { type: "trend", direction: "bullish", strength: 0.8 } },
  {},
  {},
  {},
  {
    TREND: { type: "trend", direction: "bullish", strength: 0.9 },
    SWING: {
      type: "swing",
      swings: [
        { price: 118, index: 4, type: "high" },
        { price: 109, index: 5, type: "low" },
      ],
    },
  },
  {},
  {},
];

// --- Tests ---
let passed = 0;
let failed = 0;

function test(name, fn) {
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

function assertClose(actual, expected, tolerance, msg) {
  tolerance = tolerance || 0.01;
  if (Math.abs(actual - expected) > tolerance) {
    throw new Error(
      `${msg || ""} expected ${expected} ≈ ${actual}, diff ${Math.abs(actual - expected)} > ${tolerance}`,
    );
  }
}

console.log("\nAppModel Tests\n");

let model;

// --- Constructor ---
test("constructs with all data", () => {
  model = new AppModel({
    CANDLES,
    CANDLES_BY_TF,
    FRAMES,
    EMA_SERIES,
    ATR_DATA,
    SR_DATA,
    TRADES,
    PULLBACKS,
    FACTS_DATA,
    INITIAL_BALANCE: 10000,
    MIN_TOUCHES: 2,
  });
  assert.strictEqual(model.currentFrame, 0);
  assert.strictEqual(model.activeTF, "1d");
  assert.strictEqual(model.playing, false);
  assert.strictEqual(model.futureVisibility, "hide");
  assert.strictEqual(model.frames.length, 6);
  assert.strictEqual(model.candles.length, 10);
  assert.strictEqual(model.trades.length, 4);
});

test("constructs with empty data", () => {
  const m = new AppModel({});
  assert.strictEqual(m.currentFrame, 0);
  assert.strictEqual(m.activeTF, "1d");
  assert.strictEqual(m.frames.length, 0);
  assert.strictEqual(m.candles.length, 0);
  assert.strictEqual(m.trades.length, 0);
});

// --- Candle access ---
test("activeCandles returns primary TF candles by default", () => {
  assert.strictEqual(model.activeCandles, model.candles);
  assert.strictEqual(model.activeCandles.length, 10);
});

test("activeCandles returns per-TF candles after switch", () => {
  model.switchTF("1w");
  assert.strictEqual(model.activeCandles, CANDLES_BY_TF["1w"]);
  assert.strictEqual(model.activeCandles.length, 2);
  model.switchTF("1d"); // restore
});

test("isPrimaryTF returns true for primary timeframe", () => {
  model.activeTF = "1d";
  assert.strictEqual(model.isPrimaryTF(), true);
});

test("isPrimaryTF returns false for non-primary timeframe", () => {
  model.activeTF = "1w";
  assert.strictEqual(model.isPrimaryTF(), false);
  model.activeTF = "1d";
});

// --- Frame navigation ---
test("goNext advances frame", () => {
  model.currentFrame = 0;
  assert.strictEqual(model.goNext(), 1);
  assert.strictEqual(model.currentFrame, 1);
});

test("goNext clamps at last frame", () => {
  model.currentFrame = model.frames.length - 1;
  assert.strictEqual(model.goNext(), model.frames.length - 1);
});

test("goPrev goes back", () => {
  model.currentFrame = 3;
  assert.strictEqual(model.goPrev(), 2);
  assert.strictEqual(model.currentFrame, 2);
});

test("goPrev clamps at 0", () => {
  model.currentFrame = 0;
  assert.strictEqual(model.goPrev(), 0);
  assert.strictEqual(model.currentFrame, 0);
});

test("goFirst sets frame 0", () => {
  model.currentFrame = 4;
  model.goFirst();
  assert.strictEqual(model.currentFrame, 0);
});

test("goLast sets last frame", () => {
  model.goLast();
  assert.strictEqual(model.currentFrame, model.frames.length - 1);
});

test("goTo sets specific frame", () => {
  model.goTo(2);
  assert.strictEqual(model.currentFrame, 2);
  model.goTo(10);
  assert.strictEqual(model.currentFrame, model.frames.length - 1);
  model.goTo(-1);
  assert.strictEqual(model.currentFrame, 0);
});

test("goToTime jumps to the frame for a clicked candle time", () => {
  const target = model.frameTime(4);
  model.goToTime(target);
  assert.ok(model.currentFrame >= 4);
  assert.strictEqual(model.frameTime(model.currentFrame), target);
  model.goTo(0);
  model.goToTime("1900-01-01"); // before all data → earliest frame
  assert.strictEqual(model.currentFrame, 0);
});

// --- Step sizing (coarser view TF) ---
test("nextStepIndex advances 1 frame when view TF matches frame TF", () => {
  assert.strictEqual(model.nextStepIndex(0), 1);
  assert.strictEqual(model.nextStepIndex(3), 4);
});

test("nextStepIndex advances to next visible candle on 1w view", () => {
  model.switchTF("1w");
  assert.strictEqual(model.nextStepIndex(0), 4); // weekly bar 2024-01-06 revealed at frame 4
  assert.strictEqual(model.nextStepIndex(4), model.frames.length - 1); // no further weekly bar
  model.switchTF("1d");
});

test("prevStepIndex steps 1 frame back when view TF matches frame TF", () => {
  assert.strictEqual(model.prevStepIndex(3), 2);
  assert.strictEqual(model.prevStepIndex(0), 0);
});

test("prevStepIndex lands before current weekly candle on 1w view", () => {
  model.switchTF("1w");
  assert.strictEqual(model.prevStepIndex(4), 3); // before weekly bar 2024-01-06
  assert.strictEqual(model.prevStepIndex(0), 0);
  model.switchTF("1d");
});

// --- Frame queries ---
test("frameTime returns time string", () => {
  assert.strictEqual(model.frameTime(0), "2024-01-01");
  assert.strictEqual(model.frameTime(5), "2024-01-10");
  assert.strictEqual(model.frameTime(-1), null);
  assert.strictEqual(model.frameTime(999), null);
});

test("frameFacts returns facts at frame", () => {
  assert.deepStrictEqual(model.frameFacts(0), {});
  const f2 = model.frameFacts(2);
  assert.strictEqual(f2.PB.type, "pullback");
  assert.strictEqual(f2.PB.status, "detected");
});

test("frameFacts hydrates deduped swing facts from SWING_POINTS", () => {
  const m = new AppModel({
    AVAILABLE_TFS: ["1d"],
    FACTS_DATA: [{ swing_1d: { type: "swing", swings: ["2024-01-05"], timeframe: "1d" } }],
    SWING_POINTS: {
      "1d": {
        "2024-01-05": { price: 120, index: 4, type: "high", time: "2024-01-05" },
      },
    },
  });
  const facts = m.frameFacts(0);
  const sw = facts.swing_1d;
  assert.strictEqual(sw.type, "swing");
  assert.strictEqual(sw.swings.length, 1);
  assert.deepStrictEqual(sw.swings[0], {
    price: 120,
    index: 4,
    type: "high",
    time: "2024-01-05",
  });
});

test("frameFacts passes through full-form swing facts untouched", () => {
  const m = new AppModel({
    AVAILABLE_TFS: ["1d"],
    FACTS_DATA: [
      {
        swing_1d: {
          type: "swing",
          swings: [{ price: 120, index: 4, type: "high", time: "2024-01-05" }],
          timeframe: "1d",
        },
      },
    ],
    SWING_POINTS: {},
  });
  const facts = m.frameFacts(0);
  assert.strictEqual(facts.swing_1d.swings[0].price, 120);
});

test("srLevelsAt returns levels", () => {
  assert.strictEqual(model.srLevelsAt(0).length, 0);
  const levels = model.srLevelsAt(4);
  assert.strictEqual(levels.length, 2);
  assert.strictEqual(levels[0].price, 100);
  assert.strictEqual(levels[1].price, 115);
});

test("evidenceAt returns frame evidence", () => {
  const ev = model.evidenceAt(0);
  assert.strictEqual(ev.length, 1);
  assert.strictEqual(ev[0].text, "Trend up");
  assert.strictEqual(model.evidenceAt(5).length, 0);
});

test("evidenceAt merges signals and risk evidence", () => {
  const model2 = new AppModel({
    CANDLES,
    CANDLES_BY_TF,
    AVAILABLE_TFS: ["1d"],
    FRAMES: [
      {
        time: "2024-01-01",
        evidence: [],
        signals: [
          {
            direction: "bullish",
            confidence: 0.8,
            source: "PullbackSignal",
            entry_zone: [100, 102],
          },
        ],
        risk_evidence: [
          {
            text: "Rejected: no valid RR in [1.0, 4.0] without crossing S/R",
            level: "warning",
            source: "RiskEngine",
          },
        ],
      },
    ],
  });
  const ev = model2.evidenceAt(0);
  assert.strictEqual(ev.length, 2);
  assert.strictEqual(ev[0].level, "signal");
  assert.ok(ev[0].text.includes("bullish"));
  assert.strictEqual(ev[1].level, "warning");
  assert.ok(ev[1].text.includes("Rejected"));
});

// --- Trade queries ---
test("activeTradesAt returns open trades at frame time", () => {
  model.goTo(0);
  let trades = model.activeTradesAt("2024-01-01");
  assert.strictEqual(trades.length, 0);

  model.goTo(3); // frame time = 2024-01-05
  trades = model.activeTradesAt("2024-01-05");
  assert.strictEqual(trades.length, 1); // trade 2 active (entry 01-05, exit 01-07)
  assert.strictEqual(trades[0].entry, 115);

  model.goTo(1); // frame time = 2024-01-02
  trades = model.activeTradesAt("2024-01-02");
  assert.strictEqual(trades.length, 1); // trade 1 active (entry 01-02, exit 01-04)
});

test("closedTradesBefore returns trades closed before frame", () => {
  model.goTo(0);
  let closed = model.closedTradesBefore("2024-01-01");
  assert.strictEqual(closed.length, 0);

  model.goTo(4); // frame time = 2024-01-08
  closed = model.closedTradesBefore("2024-01-08");
  assert.strictEqual(closed.length, 2); // trades 1 and 2 are closed
  assert.strictEqual(closed[0].pnl, 300);
  assert.strictEqual(closed[1].pnl, -250);
});

test("active trades excludes exited and not-yet-entered trades", () => {
  const trades = model.activeTradesAt("2024-01-06");
  // Trade 1 exited 2024-01-04, not active
  // Trade 2 entered 2024-01-05, exits 2024-01-07, active
  // Trade 3 enters 2024-01-08, not yet active
  // Trade 4 enters 2024-01-09, not yet active
  assert.strictEqual(trades.length, 1);
  assert.strictEqual(trades[0].entry, 115);
});

// --- Significant-event navigation ---
// Generic per-frame analyzer evidence exists on every candle, so event
// indices cover only signals, risk decisions, and trade entry/exit frames.
test("eventIndices covers signal/risk frames and trade entry/exit frames", () => {
  assert.deepStrictEqual(model.eventIndices(), [1, 3, 4, 5]);
});

test("nextEventIndex returns next event after frame", () => {
  assert.strictEqual(model.nextEventIndex(0), 1);
  assert.strictEqual(model.nextEventIndex(2), 3);
  assert.strictEqual(model.nextEventIndex(4), 5);
  assert.strictEqual(model.nextEventIndex(5), null);
});

test("prevEventIndex returns previous event before frame", () => {
  assert.strictEqual(model.prevEventIndex(5), 4);
  assert.strictEqual(model.prevEventIndex(4), 3);
  assert.strictEqual(model.prevEventIndex(3), 1);
  assert.strictEqual(model.prevEventIndex(1), null);
  assert.strictEqual(model.prevEventIndex(0), null);
});

// --- Summary ---
test("computeSummary returns correct stats at start", () => {
  const s = model.computeSummary("2024-01-01");
  assert.strictEqual(s.balance, 10000);
  assert.strictEqual(s.pnl, 0);
  assert.strictEqual(s.wins, 0);
  assert.strictEqual(s.losses, 0);
  assert.strictEqual(s.breakevens, 0);
  assert.strictEqual(s.totalClosed, 0);
});

test("computeSummary after first trade", () => {
  const s = model.computeSummary("2024-01-05");
  assertClose(s.balance, 10300, 0.01);
  assertClose(s.pnl, 300, 0.01);
  assert.strictEqual(s.wins, 1);
  assert.strictEqual(s.losses, 0);
  assertClose(s.winRate, 100, 0.01);
  assertClose(s.returnPct, 3.0, 0.01);
});

test("computeSummary after two trades", () => {
  const s = model.computeSummary("2024-01-08");
  assertClose(s.balance, 10050, 0.01);
  assertClose(s.pnl, 50, 0.01);
  assert.strictEqual(s.wins, 1);
  assert.strictEqual(s.losses, 1);
  assertClose(s.winRate, 50, 0.01);
  assertClose(s.profitFactor, 1.2, 0.01); // 300/250
  assertClose(s.avgWin, 300, 0.01);
  assertClose(s.avgLoss, -250, 0.01);
  assertClose(s.expectancy, 25, 0.01); // 50/2
});

test("computeSummary with breakeven trade", () => {
  const s = model.computeSummary("2024-01-10");
  assertClose(s.balance, 10050, 0.01);
  assert.strictEqual(s.wins, 1);
  assert.strictEqual(s.losses, 1);
  assert.strictEqual(s.breakevens, 1);
  assert.strictEqual(s.totalClosed, 3);
  assertClose(s.winRate, 50, 0.01); // 1 win / 2 win+loss
});

test("computeSummary drawdown calculation", () => {
  const s = model.computeSummary("2024-01-10");
  // Peak was 10300 (after trade 1), then dropped to 10050
  assertClose(s.drawdown, (10300 - 10050) / 10300, 0.001);
});

test("profitFactor infinity when no loss", () => {
  const s = model.computeSummary("2024-01-04");
  assert.strictEqual(s.profitFactor, Infinity);
});

// --- Future visibility ---
test("toggleFutureVisibility cycles modes", () => {
  assert.strictEqual(model.futureVisibility, "hide");
  assert.strictEqual(model.toggleFutureVisibility(), "dim");
  assert.strictEqual(model.toggleFutureVisibility(), "show");
  assert.strictEqual(model.toggleFutureVisibility(), "hide");
});

// --- TF switching ---
test("switchTF changes active timeframe", () => {
  assert.strictEqual(model.activeTF, "1d");
  const ok = model.switchTF("1w");
  assert.strictEqual(ok, true);
  assert.strictEqual(model.activeTF, "1w");
  model.switchTF("1d");
});

test("switchTF returns false for unknown tf", () => {
  const ok = model.switchTF("1h");
  assert.strictEqual(ok, false);
  assert.strictEqual(model.activeTF, "1d"); // unchanged
});

// --- _t helper ---
test("_t parses ISO date string to ms timestamp", () => {
  const ts = _t("2024-01-01");
  assert.strictEqual(typeof ts, "number");
  assert.strictEqual(ts, Date.parse("2024-01-01"));
});

test("_t handles ISO datetime string", () => {
  const ts = _t("2024-01-01T00:00:00");
  assert.strictEqual(ts, Date.parse("2024-01-01"));
});

// --- _fmtP price precision ---
test("_fmtP keeps 2dp for large prices", () => {
  assert.strictEqual(_fmtP(60234.567), "60234.57");
});

test("_fmtP uses 4dp for mid-range prices", () => {
  assert.strictEqual(_fmtP(1.10456), "1.1046");
});

test("_fmtP uses 6dp for sub-1 prices", () => {
  assert.strictEqual(_fmtP(0.01234567), "0.012346");
});

test("_fmtP trims trailing zeros but keeps >=2dp", () => {
  assert.strictEqual(_fmtP(1.1), "1.1000");
  assert.strictEqual(_fmtP(0.05), "0.05");
  assert.strictEqual(_fmtP(100.0), "100.00");
});

test("_fmtP handles null/undefined", () => {
  assert.strictEqual(_fmtP(null), "");
  assert.strictEqual(_fmtP(undefined), "");
});

console.log(`\n${passed} passed, ${failed} failed, ${passed + failed} total\n`);
process.exit(failed > 0 ? 1 : 0);
