'use strict';

const assert = require('assert');
const { installBrowserMocks, installFakeTimers, keyEvent } = require('./mock_helpers.js');
const { makeModel, FRAMES } = require('./sample_data.js');
const {
  PlaybackController, KeyboardController, TFController,
} = require('../../src/marketatlas/visualization/base/controllers.js');

installBrowserMocks();
const timers = installFakeTimers();

let passed = 0;
let failed = 0;

function test(name, fn) {
  timers.reset();
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

console.log('\nPlaybackController Tests\n');

test('togglePlaying starts playback with configured speed', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 150, render: () => {} });
  pb.togglePlaying();
  assert.strictEqual(model.playing, true);
  assert.strictEqual(timers.count(), 1);
  assert.deepStrictEqual(timers.delays(), [150]);
  pb.togglePlaying();
  assert.strictEqual(model.playing, false);
  assert.strictEqual(timers.count(), 0);
});

test('interval tick advances frame and re-renders', () => {
  const model = makeModel();
  let renders = 0;
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => { renders++; } });
  pb.togglePlaying();
  const [id] = timers.ids();
  timers.fire(id);
  assert.strictEqual(model.currentFrame, 1);
  assert.strictEqual(renders, 1);
  timers.fire(id);
  assert.strictEqual(model.currentFrame, 2);
  assert.strictEqual(renders, 2);
  pb.togglePlaying();
});

test('playback auto-pauses at last frame', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 50, render: () => {} });
  model.goLast();
  pb.togglePlaying();
  const [id] = timers.ids();
  timers.fire(id);
  assert.strictEqual(model.playing, false);
  assert.strictEqual(timers.count(), 0);
});

test('stepForward advances and pauses', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  pb.togglePlaying(); // start playback
  assert.strictEqual(model.playing, true);
  pb.stepForward();
  assert.strictEqual(model.currentFrame, 1);
  assert.strictEqual(model.playing, false);
  assert.strictEqual(timers.count(), 0);
});

test('stepBackward goes back and clamps at 0', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  model.goTo(3);
  pb.stepBackward();
  assert.strictEqual(model.currentFrame, 2);
  model.goFirst();
  pb.stepBackward();
  assert.strictEqual(model.currentFrame, 0);
});

test('stepping on a coarser TF advances to the next visible candle', () => {
  const model = makeModel();
  model.switchTF('1w');
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  pb.stepForward(); // weekly bar 2024-01-06 first becomes visible at frame 4
  assert.strictEqual(model.currentFrame, 4);
  pb.stepForward(); // no weekly bar after frame 4's date in this fixture
  assert.strictEqual(model.currentFrame, model.frames.length - 1);
});

test('stepping back on a coarser TF lands before the current weekly candle', () => {
  const model = makeModel();
  model.switchTF('1w');
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  model.goTo(4);
  pb.stepBackward(); // last frame before weekly bar 2024-01-06
  assert.strictEqual(model.currentFrame, 3);
});

test('jumpToStart and jumpToEnd pause and position', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  model.goTo(3);
  pb.jumpToStart();
  assert.strictEqual(model.currentFrame, 0);
  pb.jumpToEnd();
  assert.strictEqual(model.currentFrame, model.frames.length - 1);
  assert.strictEqual(model.playing, false);
  assert.strictEqual(timers.count(), 0);
});

test('setSpeed changes interval delay', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 150, render: () => {} });
  pb.setSpeed(1000);
  pb.togglePlaying();
  assert.deepStrictEqual(timers.delays(), [1000]);
  pb.togglePlaying();
});

test('toggleFutureVisibility cycles modes and re-renders', () => {
  const model = makeModel();
  let renders = 0;
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => { renders++; } });
  assert.strictEqual(model.futureVisibility, 'hide');
  assert.strictEqual(pb.toggleFutureVisibility(), 'dim');
  assert.strictEqual(model.futureVisibility, 'dim');
  assert.strictEqual(pb.toggleFutureVisibility(), 'show');
  assert.strictEqual(pb.toggleFutureVisibility(), 'hide');
  assert.strictEqual(renders, 3);
});

console.log('\nKeyboardController Tests\n');

test('arrow keys step frames', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  const kb = new KeyboardController(pb);
  document.dispatch('keydown', keyEvent('ArrowRight'));
  assert.strictEqual(model.currentFrame, 1);
  document.dispatch('keydown', keyEvent('ArrowRight'));
  assert.strictEqual(model.currentFrame, 2);
  document.dispatch('keydown', keyEvent('ArrowLeft'));
  assert.strictEqual(model.currentFrame, 1);
  kb.destroy();
});

test('space toggles play/pause', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  const kb = new KeyboardController(pb);
  document.dispatch('keydown', keyEvent(' '));
  assert.strictEqual(model.playing, true);
  document.dispatch('keydown', keyEvent(' '));
  assert.strictEqual(model.playing, false);
  kb.destroy();
});

test('Home and End jump to bounds', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  const kb = new KeyboardController(pb);
  model.goTo(2);
  document.dispatch('keydown', keyEvent('Home'));
  assert.strictEqual(model.currentFrame, 0);
  document.dispatch('keydown', keyEvent('End'));
  assert.strictEqual(model.currentFrame, model.frames.length - 1);
  kb.destroy();
});

test('f key toggles future visibility', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  const kb = new KeyboardController(pb);
  document.dispatch('keydown', keyEvent('f'));
  assert.strictEqual(model.futureVisibility, 'dim');
  document.dispatch('keydown', keyEvent('F'));
  assert.strictEqual(model.futureVisibility, 'show');
  kb.destroy();
});

test('a key toggles auto-scroll via callback', () => {
  const toggles = [];
  const kb = new KeyboardController(null, { toggleAutoscroll: () => toggles.push('toggled') });
  document.dispatch('keydown', keyEvent('a'));
  document.dispatch('keydown', keyEvent('A'));
  assert.deepStrictEqual(toggles, ['toggled', 'toggled']);
  kb.destroy();
});

test('a key is a no-op without callback', () => {
  const kb = new KeyboardController(null, {});
  assert.doesNotThrow(() => document.dispatch('keydown', keyEvent('a')));
  kb.destroy();
});

test('ignores keys when typing in an input', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  const kb = new KeyboardController(pb);
  document.dispatch('keydown', keyEvent('ArrowRight', { tagName: 'INPUT' }));
  assert.strictEqual(model.currentFrame, 0);
  document.dispatch('keydown', keyEvent(' ', { tagName: 'TEXTAREA' }));
  assert.strictEqual(model.playing, false);
  kb.destroy();
});

test('destroy removes the keydown listener', () => {
  const model = makeModel();
  const pb = new PlaybackController(model, {}, { speed: 100, render: () => {} });
  const kb = new KeyboardController(pb);
  kb.destroy();
  document.dispatch('keydown', keyEvent('ArrowRight'));
  assert.strictEqual(model.currentFrame, 0);
});

console.log('\nTFController Tests\n');

function makeSpyViews() {
  const chart = {};
  const calls = {};
  ['updateCandles', 'updateVolume', 'updateEMAs', 'updateATR', 'updateSR',
   'updateTrades', 'updateZigzag', 'updateMarkers', 'scrollToFrame'].forEach(m => {
    calls[m] = [];
    chart[m] = (idx) => { calls[m].push(idx); };
  });
  calls.getVisibleTimeRange = [];
  calls.setVisibleTimeRange = [];
  chart.getVisibleTimeRange = () => { calls.getVisibleTimeRange.push('call'); return null; };
  chart.setVisibleTimeRange = (r) => { calls.setVisibleTimeRange.push(r); };
  const panels = {};
  ['info', 'evidence', 'summary'].forEach(name => {
    const c = [];
    panels[name] = { updateCalls: c, update: (m, idx) => { c.push(idx); } };
  });
  const tc = [];
  panels.timeline = { updateCalls: tc, updateCursor: (m, idx) => { tc.push(idx); } };
  return { chart, calls, panels };
}

function makeBackend(model) {
  const backend = {
    loadCalls: [],
    rebuildCalls: [],
    loadTFData(tf) { this.loadCalls.push(tf); return model.candlesByTF[tf] !== undefined; },
    rebuildCharts(tf) { this.rebuildCalls.push(tf); },
  };
  return backend;
}

test('switchTF reloads data, rebuilds charts and refreshes views', () => {
  const model = makeModel();
  const { chart, calls, panels } = makeSpyViews();
  const backend = makeBackend(model);
  const ctrl = new TFController(model, {
    chart, info: panels.info, evidence: panels.evidence,
    summary: panels.summary, timeline: panels.timeline,
  }, backend);
  model.goTo(2);
  ctrl.switchTF('1w');
  assert.deepStrictEqual(backend.loadCalls, ['1w']);
  assert.deepStrictEqual(backend.rebuildCalls, ['1w']);
  assert.strictEqual(model.activeTF, '1w');
  assert.strictEqual(model.currentFrame, 2);
  assert.deepStrictEqual(calls.updateCandles, [2]);
  assert.deepStrictEqual(calls.updateEMAs, [2]);
  assert.deepStrictEqual(calls.scrollToFrame, [2]);
  assert.deepStrictEqual(panels.info.updateCalls, [2]);
  assert.deepStrictEqual(panels.evidence.updateCalls, [2]);
  assert.deepStrictEqual(panels.summary.updateCalls, [2]);
  assert.deepStrictEqual(panels.timeline.updateCalls, [2]);
});

test('switchTF to same TF is a no-op', () => {
  const model = makeModel();
  const { chart, panels } = makeSpyViews();
  const backend = makeBackend(model);
  const ctrl = new TFController(model, {
    chart, info: panels.info, evidence: panels.evidence,
    summary: panels.summary, timeline: panels.timeline,
  }, backend);
  ctrl.switchTF('1d'); // already active
  assert.deepStrictEqual(backend.loadCalls, []);
  assert.deepStrictEqual(backend.rebuildCalls, []);
  assert.strictEqual(model.activeTF, '1d');
});

test('switchTF to unknown TF is ignored', () => {
  const model = makeModel();
  const { chart, calls, panels } = makeSpyViews();
  const backend = makeBackend(model);
  const ctrl = new TFController(model, {
    chart, info: panels.info, evidence: panels.evidence,
    summary: panels.summary, timeline: panels.timeline,
  }, backend);
  ctrl.switchTF('1h');
  assert.deepStrictEqual(backend.loadCalls, ['1h']);
  assert.deepStrictEqual(backend.rebuildCalls, []);
  assert.strictEqual(model.activeTF, '1d');
  assert.deepStrictEqual(calls.updateCandles, []);
});

test('switchTF preserves the visible time range across TF switch', () => {
  const model = makeModel();
  const { chart, calls, panels } = makeSpyViews();
  const range = { from: '2024-01-01', to: '2024-02-01' };
  chart.getVisibleTimeRange = () => range;
  const backend = makeBackend(model);
  const ctrl = new TFController(model, {
    chart, info: panels.info, evidence: panels.evidence,
    summary: panels.summary, timeline: panels.timeline,
  }, backend);
  model.goTo(2);
  ctrl.switchTF('1w');
  // Same horizontal span restored on the new chart; no scroll override.
  assert.deepStrictEqual(calls.setVisibleTimeRange, [range]);
  assert.deepStrictEqual(calls.scrollToFrame, []);
  assert.deepStrictEqual(calls.updateCandles, [2]);
});

test('switchTF falls back to scrollToFrame when no visible range available', () => {
  const model = makeModel();
  const { chart, calls, panels } = makeSpyViews();
  const backend = makeBackend(model);
  const ctrl = new TFController(model, {
    chart, info: panels.info, evidence: panels.evidence,
    summary: panels.summary, timeline: panels.timeline,
  }, backend);
  model.goTo(2);
  ctrl.switchTF('1w');
  assert.deepStrictEqual(calls.setVisibleTimeRange, []);
  assert.deepStrictEqual(calls.scrollToFrame, [2]);
});

test('switchTF round-trips back to primary TF', () => {
  const model = makeModel();
  const { chart, calls, panels } = makeSpyViews();
  const backend = makeBackend(model);
  const ctrl = new TFController(model, {
    chart, info: panels.info, evidence: panels.evidence,
    summary: panels.summary, timeline: panels.timeline,
  }, backend);
  ctrl.switchTF('1w');
  ctrl.switchTF('1d');
  assert.deepStrictEqual(backend.loadCalls, ['1w', '1d']);
  assert.deepStrictEqual(backend.rebuildCalls, ['1w', '1d']);
  assert.strictEqual(model.activeTF, '1d');
  assert.strictEqual(calls.updateCandles.length, 2);
});

console.log(`\n${passed} passed, ${failed} failed, ${passed + failed} total\n`);
process.exit(failed > 0 ? 1 : 0);
