'use strict';

// Browser + LightweightCharts mocks for running views/controllers tests in Node.

function createEl(id) {
  const set = new Set();
  return {
    id,
    innerHTML: '',
    textContent: '',
    className: '',
    style: {},
    clientWidth: 800,
    clientHeight: 500,
    _listeners: {},
    classList: {
      add(...c) { c.forEach(x => set.add(x)); },
      remove(...c) { c.forEach(x => set.delete(x)); },
      toggle(c, force) {
        if (force === true) set.add(c);
        else if (force === false) set.delete(c);
        else if (set.has(c)) set.delete(c); else set.add(c);
      },
      contains(c) { return set.has(c); },
    },
    addEventListener(type, cb) { (this._listeners[type] = this._listeners[type] || []).push(cb); },
    removeEventListener(type, cb) {
      const a = this._listeners[type];
      if (a) { const i = a.indexOf(cb); if (i >= 0) a.splice(i, 1); }
    },
    dispatch(type, event) { (this._listeners[type] || []).slice().forEach(cb => cb(event)); },
  };
}

class MockSeries {
  constructor(opts) {
    this.opts = opts || {};
    this._data = [];
    this.markers = [];
    this.priceLines = [];
  }
  setData(d) { this._data = d; }
  update(d) { this._data = this._data.concat(d); }
  applyOptions(o) { Object.assign(this.opts, o); }
  setMarkers(m) { this.markers = m; }
  data() { return this._data; }
  createPriceLine(o) {
    const pl = Object.assign({ removed: false }, o);
    pl.remove = () => { pl.removed = true; };
    this.priceLines.push(pl);
    return pl;
  }
  removePriceLine(pl) { pl.removed = true; }
}

class MockChart {
  constructor(el, opts) {
    this.el = el;
    this.opts = opts || {};
    this.removed = false;
    this.series = [];
    this.rangeHandlers = [];
    this.crosshair = null;
  }
  addCandlestickSeries(o) { const s = new MockSeries(o); this.series.push(s); return s; }
  addLineSeries(o) { const s = new MockSeries(o); this.series.push(s); return s; }
  addHistogramSeries(o) { const s = new MockSeries(o); this.series.push(s); return s; }
  remove() { this.removed = true; }
  timeScale() { return this; }
  subscribeVisibleLogicalRangeChange(cb) { this.rangeHandlers.push(cb); }
  setVisibleLogicalRange() {}
  getVisibleLogicalRange() { return { from: 0, to: 10 }; }
  getVisibleRange() { return this.visibleRange || { from: '2024-01-01', to: '2024-01-10' }; }
  setVisibleRange(range) {
    this.visibleRange = range;
    this.rangeHandlers.forEach(cb => cb({ from: 0, to: 10 }));
  }
  scrollToTime() {}
  scrollToPosition() {}
  setCrosshairPosition(price, time, series) { this.crosshair = { price, time, series }; }
  applyOptions(o) { Object.assign(this.opts, o); }
}

const els = {};
const documentMock = {
  _listeners: {},
  getElementById(id) { if (!els[id]) els[id] = createEl(id); return els[id]; },
  addEventListener(type, cb) { (this._listeners[type] = this._listeners[type] || []).push(cb); },
  removeEventListener(type, cb) {
    const a = this._listeners[type];
    if (a) { const i = a.indexOf(cb); if (i >= 0) a.splice(i, 1); }
  },
  dispatch(type, event) { (this._listeners[type] || []).slice().forEach(cb => cb(event)); },
};

function installBrowserMocks() {
  global._t = (t) => Date.parse(t);
  global.window = global.window || {};
  global.LightweightCharts = {
    CrosshairMode: { Normal: 0 },
    LineStyle: { Solid: 0, Dashed: 1, Dotted: 2 },
    createdCharts: [],
    createChart(el, opts) {
      const c = new MockChart(el, opts);
      this.createdCharts.push(c);
      return c;
    },
  };
  global.document = documentMock;
}

function resetBrowserMocks() {
  global.LightweightCharts.createdCharts.length = 0;
  for (const k of Object.keys(els)) delete els[k];
  documentMock._listeners = {};
}

function installFakeTimers() {
  const registry = new Map();
  let nextId = 1;
  const fake = {
    setInterval(cb, delay) { const id = nextId++; registry.set(id, { cb, delay }); return id; },
    clearInterval(id) { registry.delete(id); },
    fire(id) { const t = registry.get(id); if (t) t.cb(); },
    ids() { return Array.from(registry.keys()); },
    delays() { return Array.from(registry.values()).map(t => t.delay); },
    count() { return registry.size; },
    reset() { registry.clear(); nextId = 1; },
  };
  global.setInterval = fake.setInterval;
  global.clearInterval = fake.clearInterval;
  return fake;
}

function keyEvent(key, target) {
  return {
    key,
    target: target || { tagName: 'BODY' },
    preventDefault() { this._prevented = true; },
  };
}

module.exports = {
  MockChart, MockSeries, createEl,
  installBrowserMocks, resetBrowserMocks, installFakeTimers, keyEvent,
};
