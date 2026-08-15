"use strict";

const { AppModel } = require("../../src/marketatlas/visualization/base/models.js");

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
    { time: "2024-01-20", open: 126, high: 134, low: 120, close: 128, volume: 6100 },
    { time: "2024-01-27", open: 128, high: 136, low: 124, close: 130, volume: 6500 },
    { time: "2024-02-03", open: 130, high: 138, low: 126, close: 132, volume: 6200 },
    { time: "2024-02-10", open: 132, high: 140, low: 128, close: 134, volume: 6800 },
  ],
};

const AVAILABLE_TFS = ["1d", "1w"];

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
      swing_pattern_times: ["2024-01-02", "2024-01-03", "2024-01-04"],
    },
    SWINGSTRUCT: {
      type: "swingstructure",
      direction: "bullish",
      points: [
        { time: "2024-01-02", price: 108 },
        { time: "2024-01-03", price: 106 },
        { time: "2024-01-04", price: 111 },
      ],
    },
  },
  {
    TREND: { type: "trend", direction: "bullish", strength: 0.8 },
    SWINGW: {
      type: "swing",
      timeframe: "1w",
      swings: [{ price: 119, index: 0, type: "high", time: "2024-01-06" }],
    },
  },
  {},
  {
    TREND: { type: "trend", direction: "bullish", strength: 0.9 },
    SWING: {
      type: "swing",
      timeframe: "1d",
      swings: [
        { price: 118, index: 4, type: "high", time: "2024-01-05" },
        { price: 109, index: 5, type: "low", time: "2024-01-06" },
      ],
    },
  },
  {},
  {},
  {},
  {},
  {},
  {},
];

const DEFAULT_OPTS = { INITIAL_BALANCE: 10000, MIN_TOUCHES: 2, MAX_HOLD_DAYS: 10 };

function makeModel(opts) {
  const o = Object.assign({}, DEFAULT_OPTS, opts || {});
  return new AppModel({
    CANDLES,
    CANDLES_BY_TF,
    AVAILABLE_TFS,
    FRAMES,
    EMA_SERIES,
    ATR_DATA,
    SR_DATA,
    TRADES,
    PULLBACKS,
    FACTS_DATA,
    EVIDENCE_MAP: {},
    INITIAL_BALANCE: o.INITIAL_BALANCE,
    MIN_TOUCHES: o.MIN_TOUCHES,
    MAX_HOLD_DAYS: o.MAX_HOLD_DAYS,
  });
}

module.exports = {
  CANDLES,
  CANDLES_BY_TF,
  AVAILABLE_TFS,
  FRAMES,
  EMA_SERIES,
  ATR_DATA,
  SR_DATA,
  TRADES,
  PULLBACKS,
  FACTS_DATA,
  makeModel,
};
