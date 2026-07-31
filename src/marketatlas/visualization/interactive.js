// @data declarations (replaced by Python generator)
const CANDLES = null; // @data:CANDLES
const CANDLES_BY_TF = null; // @data:CANDLES_BY_TF
const AVAILABLE_TFS = null; // @data:AVAILABLE_TFS
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

// --- Init ---
;(function() {
  const model = new AppModel({
    CANDLES, CANDLES_BY_TF, AVAILABLE_TFS, FRAMES,
    EMA_SERIES, ATR_DATA, SR_DATA, TRADES, PULLBACKS,
    FACTS_DATA, EVIDENCE_MAP, INITIAL_BALANCE, MIN_TOUCHES,
  });

  const containers = {
    main: document.getElementById('chart-container'),
    atr: document.getElementById('atr-container'),
    volume: document.getElementById('volume-container'),
  };

  const chartView = new ChartView(model, containers);
  const infoPanelView = new InfoPanelView('info-content');
  const evidencePanelView = new EvidencePanelView('evidence-content');
  const summaryBarView = new SummaryBarView();
  const timelineBarView = new TimelineBarView('timeline-bar');

  const views = { chart: chartView, info: infoPanelView, evidence: evidencePanelView, summary: summaryBarView, timeline: timelineBarView };

  function render() {
    const idx = model.currentFrame;
    chartView.updateCandles(idx);
    chartView.updateVolume(idx);
    chartView.updateEMAs(idx);
    chartView.updateATR(idx);
    chartView.updateSR(idx);
    chartView.updateTrades(idx);
    chartView.updateZigzag(idx);
    chartView.updateMarkers(idx);
    chartView.setCrosshair(idx);
    if (!model.autoScrollDisabled) chartView.scrollToFrame(idx);
    infoPanelView.update(model, idx);
    evidencePanelView.update(model, idx);
    summaryBarView.update(model, idx);
    timelineBarView.updateCursor(model, idx);
    document.getElementById('frame-num').textContent = String(idx + 1);
  }

  const playbackCtrl = new PlaybackController(model, views, {
    speed: 150,
    render: render,
  });

  const keyboardCtrl = new KeyboardController(playbackCtrl, {
    toggleAutoscroll: function() {
      model.autoScrollDisabled = !model.autoScrollDisabled;
      const btn = document.getElementById('btn-autoscroll');
      btn.classList.toggle('active', !model.autoScrollDisabled);
      if (!model.autoScrollDisabled) chartView.scrollToFrame(model.currentFrame);
    },
  });
  const tfCtrl = new TFController(model, views, {
    loadTFData: function(tf) {
      if (!model.candlesByTF[tf]) return false;
      model.switchTF(tf);
      return true;
    },
    rebuildCharts: function(tf) {
      chartView.build(tf);
      timelineBarView.build(model);
    },
  });

  // --- UI event binding ---
  function withAutoScroll(fn) {
    return function() {
      playbackCtrl._pause();
      model.autoScrollDisabled = false;
      document.getElementById('btn-autoscroll').classList.add('active');
      fn();
    };
  }

  document.getElementById('btn-first').addEventListener('click', withAutoScroll(() => {
    model.goFirst(); render();
  }));
  document.getElementById('btn-last').addEventListener('click', withAutoScroll(() => {
    model.goLast(); render();
  }));
  document.getElementById('btn-prev').addEventListener('click', withAutoScroll(() => {
    model.goPrev(); render();
  }));
  document.getElementById('btn-next').addEventListener('click', withAutoScroll(() => {
    model.goNext(); render();
  }));
  document.getElementById('btn-play').addEventListener('click', () => {
    model.autoScrollDisabled = false;
    document.getElementById('btn-autoscroll').classList.add('active');
    playbackCtrl.togglePlaying();
  });
  document.getElementById('speed-select').addEventListener('change', function() {
    playbackCtrl.setSpeed(parseInt(this.value, 10));
    if (model.playing) { playbackCtrl.togglePlaying(); playbackCtrl.togglePlaying(); }
  });
  document.getElementById('btn-visibility').addEventListener('click', () => {
    const mode = model.toggleFutureVisibility();
    const labels = { hide: '\u{1F441} Hide', dim: '\u{1F441}\uFE0F Dim', show: '\u{1F441}\u200D\u{1F5E1} Show' };
    document.getElementById('btn-visibility').innerHTML = labels[mode];
    render();
  });
  document.getElementById('btn-autoscroll').addEventListener('click', () => {
    model.autoScrollDisabled = !model.autoScrollDisabled;
    const btn = document.getElementById('btn-autoscroll');
    btn.classList.toggle('active', !model.autoScrollDisabled);
    if (!model.autoScrollDisabled) chartView.scrollToFrame(model.currentFrame);
  });

  // Mouse/touch interaction: disable auto-scroll
  const chartContainer = document.getElementById('chart-container');
  chartContainer.addEventListener('mousedown', () => { if (!model.playing) { model.autoScrollDisabled = true; document.getElementById('btn-autoscroll').classList.remove('active'); } });
  chartContainer.addEventListener('wheel', () => { if (!model.playing) { model.autoScrollDisabled = true; document.getElementById('btn-autoscroll').classList.remove('active'); } });
  chartContainer.addEventListener('touchstart', () => { if (!model.playing) { model.autoScrollDisabled = true; document.getElementById('btn-autoscroll').classList.remove('active'); } });

  // Resize
  window.addEventListener('resize', () => chartView.resize());

  // TF selector
  document.addEventListener('DOMContentLoaded', function() {
    const tfSelect = document.getElementById('tf-select');
    if (tfSelect) {
      tfSelect.addEventListener('change', function(e) {
        playbackCtrl._pause();
        model.autoScrollDisabled = false;
        document.getElementById('btn-autoscroll').classList.add('active');
        tfCtrl.switchTF(e.target.value);
      });
    }
  });

  // --- Init display ---
  document.getElementById('frame-total').textContent = String(model.frames.length);
  chartView.build(model.activeTF);
  timelineBarView.build(model);
  if (model.frames.length > 0) {
    render();
  } else {
    document.getElementById('info-content').innerHTML = 'No frames to display.';
    document.getElementById('evidence-content').innerHTML = 'No evidence.';
  }
})();
