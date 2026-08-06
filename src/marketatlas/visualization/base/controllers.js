/**
 * Controllers — orchestrate user input → model state → view refresh.
 */

// --- PlaybackController ---
class PlaybackController {
  constructor(model, views, opts) {
    this.model = model;
    this.views = views;           // { chart, info, evidence, summary, timeline }
    this.speed = opts.speed || 150;
    this.render = opts.render || function() {};
  }

  togglePlaying() {
    this.model.playing = !this.model.playing;
    if (this.model.playing) this._play();
    else this._pause();
  }

  _play() {
    this.model.playInterval = setInterval(() => {
      if (this.model.currentFrame >= this.model.frames.length - 1) {
        this._pause();
        return;
      }
      this.model.goNext();
      this.render();
    }, this.speed);
  }

  _pause() {
    if (this.model.playInterval) {
      clearInterval(this.model.playInterval);
      this.model.playInterval = null;
    }
    this.model.playing = false;
  }

  setSpeed(speed) { this.speed = speed; }

  stepForward() {
    this._pause();
    this.model.goTo(this.model.nextStepIndex(this.model.currentFrame));
    this.render();
  }

  stepBackward() {
    this._pause();
    this.model.goTo(this.model.prevStepIndex(this.model.currentFrame));
    this.render();
  }

  jumpToStart() {
    this._pause();
    this.model.goFirst();
    this.render();
  }

  jumpToEnd() {
    this._pause();
    this.model.goLast();
    this.render();
  }

  toggleFutureVisibility() {
    const mode = this.model.toggleFutureVisibility();
    this.render();
    return mode;
  }
}

// --- KeyboardController ---
class KeyboardController {
  constructor(playbackCtrl, opts) {
    this.pb = playbackCtrl;
    this.opts = opts || {};
    this._bound = this._handler.bind(this);
    document.addEventListener('keydown', this._bound);
  }

  _handler(e) {
    // Skip when typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;

    switch (e.key) {
      case 'ArrowRight':
        e.preventDefault();
        this.pb.stepForward();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        this.pb.stepBackward();
        break;
      case ' ':
        e.preventDefault();
        this.pb.togglePlaying();
        break;
      case 'Home':
        e.preventDefault();
        this.pb.jumpToStart();
        break;
      case 'End':
        e.preventDefault();
        this.pb.jumpToEnd();
        break;
      case 'f':
      case 'F':
        this.pb.toggleFutureVisibility();
        break;
      case 'a':
      case 'A':
        if (this.opts.toggleAutoscroll) this.opts.toggleAutoscroll();
        break;
    }
  }

  destroy() {
    document.removeEventListener('keydown', this._bound);
  }
}

// --- TFController ---
class TFController {
  constructor(model, views, backend) {
    this.model = model;
    this.views = views;
    this.backend = backend; // { rebuildCharts: (tf) => void, loadTFData: (tf) => object }
  }

  switchTF(tf) {
    if (tf === this.model.activeTF) return;
    if (!this.backend.loadTFData(tf)) return;
    const prevRange = this.views.chart.getVisibleTimeRange();
    this.model.switchTF(tf);
    this.backend.rebuildCharts(tf);
    const idx = this.model.goTo(this.model.currentFrame); // re-clamp after data change
    // Preserve the same horizontal time span across TF switch so the visible
    // date range stays constant (candles just get wider/taller per TF).
    if (prevRange) {
      this.model.programmaticScroll = true;
      this.views.chart.setVisibleTimeRange(prevRange);
      this._refreshAll(idx, false);
    } else {
      this._refreshAll(idx, true);
    }
  }

  _refreshAll(idx, scroll) {
    const v = this.views;
    v.chart.updateCandles(idx);
    v.chart.updateVolume(idx);
    v.chart.updateEMAs(idx);
    v.chart.updateATR(idx);
    v.chart.updateSR(idx);
    v.chart.updateTrades(idx);
    v.chart.updateZigzag(idx);
    v.chart.updateMarkers(idx);
    if (scroll) v.chart.scrollToFrame(idx);
    v.info.update(this.model, idx);
    v.evidence.update(this.model, idx);
    v.summary.update(this.model, idx);
    v.timeline.updateCursor(this.model, idx);
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { PlaybackController, KeyboardController, TFController };
} else {
  window.PlaybackController = PlaybackController;
  window.KeyboardController = KeyboardController;
  window.TFController = TFController;
}
