"use strict";

const _tradesRef = typeof require === "function" ? require("./trades") : null;

function _resolvedHitTradeBox(cv, point) {
  return _tradesRef ? _tradesRef.hitTradeBox(cv, point) : hitTradeBox(cv, point);
}

function onCrosshairMove(cv, param) {
  if (!param || !param.point) {
    hideTradeTooltip(cv);
    return;
  }
  const trade = _resolvedHitTradeBox(cv, param.point);
  if (trade) {
    showTradeTooltip(cv, trade, param.point);
    return;
  }
  const html = hitAnnotationTooltip(cv, param);
  if (html) {
    showTooltip(cv, html, param.point);
    return;
  }
  hideTradeTooltip(cv);
}

function _frameInfoBlock(cv, time) {
  const frame = frameAtTime(cv, time);
  if (!frame) return "";
  const sigs = frame.signals || [];
  const risk = frame.risk_evidence || [];
  const rejections = frame.signal_rejections || [];
  if (!sigs.length && !risk.length && !rejections.length) return "";
  const row = (label, value) =>
    '<div><span style="color:#94a3b8">' + label + "</span> " + value + "</div>";
  let html = "";
  sigs.forEach((s) => {
    html +=
      '<div style="font-weight:700;color:#a855f7">SIGNAL ' +
      s.direction.toUpperCase() +
      "</div>" +
      row("Confidence", (s.confidence || 0).toFixed(2)) +
      row("Source", s.source || "");
  });
  rejections.forEach((r) => {
    html +=
      '<div style="font-weight:700;color:#64748b;text-decoration:line-through">REJECTED</div>' +
      '<div style="color:#94a3b8;font-size:10px">' +
      (r.text || "no reason") +
      "</div>";
  });
  risk.forEach((r) => {
    html += '<div style="margin-top:2px;color:#e94560">' + r.text + "</div>";
  });
  return html;
}

function hitAnnotationTooltip(cv, param) {
  const row = (label, value) =>
    '<div><span style="color:#94a3b8">' + label + "</span> " + value + "</div>";
  const facts = cv.model.frameFacts(cv._frameIdx || 0);
  const pb = cv.model.pullbacks[cv._frameIdx || 0];

  const swingFacts = Object.values(facts).filter(
    (f) => f && f.type === "swing" && f.timeframe === cv.model.activeTF,
  );
  for (const sf of swingFacts) {
    for (const sw of sf.swings) {
      if (sw.time !== param.time) continue;
      const info = _frameInfoBlock(cv, param.time);
      return (
        '<div style="font-weight:700;color:' +
        (sw.type === "high" ? "#f59e0b" : "#3b82f6") +
        '">' +
        (sw.type === "high" ? "SWING HIGH" : "SWING LOW") +
        "</div>" +
        row("Price", sw.price.toFixed(2)) +
        (sw.index !== undefined ? row("Bar", sw.index) : "") +
        (info ? '<div style="margin-top:4px;border-top:1px solid #1e293b">' + info + "</div>" : "")
      );
    }
  }

  if (pb && pb.time === param.time) {
    const pbf = Object.values(facts).find((f) => f && f.type === "pullback");
    let html = '<div style="font-weight:700;color:#22c55e">PULLBACK</div>';
    if (pbf) {
      if (pbf.direction) html += row("Direction", pbf.direction);
      if (pbf.strength !== undefined && pbf.strength !== null)
        html += row("Strength", pbf.strength.toFixed(2));
      if (pbf.swing_pattern && pbf.swing_pattern.length)
        html += row("Pattern", pbf.swing_pattern.map((p) => p.toFixed(2)).join(" \u2192 "));
    }
    const info = _frameInfoBlock(cv, param.time);
    if (info) html += '<div style="margin-top:4px;border-top:1px solid #1e293b">' + info + "</div>";
    return html;
  }

  const frame = frameAtTime(cv, param.time);
  if (frame) {
    const info = _frameInfoBlock(cv, param.time);
    if (info) return info;
  }

  if (cv._srHits && cv._srHits.length) {
    let best = null;
    let bestDy = 8;
    for (const lv of cv._srHits) {
      const y = cv.candleSeries.priceToCoordinate(lv.price);
      if (y === null) continue;
      const dy = Math.abs(param.point.y - y);
      if (dy < bestDy) {
        bestDy = dy;
        best = lv;
      }
    }
    if (best) {
      return (
        '<div style="font-weight:700;color:' +
        (best.type === "support" ? "#3b82f6" : "#f59e0b") +
        '">' +
        (best.type === "support" ? "SUPPORT" : "RESISTANCE") +
        "</div>" +
        row("Price", best.price.toFixed(2)) +
        row("Strength", best.strength + " touch" + (best.strength === 1 ? "" : "es"))
      );
    }
  }
  return null;
}

function frameAtTime(cv, time) {
  if (time === undefined || time === null) return null;
  return cv.model.frames.find((f) => f.time === time) || null;
}

function ensureTooltipEl(cv) {
  if (cv._tooltipEl) return cv._tooltipEl;
  const el = document.createElement("div");
  Object.assign(el.style, {
    position: "absolute",
    zIndex: 10,
    pointerEvents: "none",
    display: "none",
    background: "rgba(10,10,20,0.92)",
    color: "#e0e0e0",
    border: "1px solid #0f3460",
    borderRadius: "4px",
    padding: "6px 8px",
    font: "11px/1.5 ui-monospace, Menlo, monospace",
    whiteSpace: "nowrap",
  });
  cv.containers.main.appendChild(el);
  cv._tooltipEl = el;
  return el;
}

function showTooltip(cv, html, point) {
  const el = ensureTooltipEl(cv);
  el.innerHTML = html;
  el.style.display = "block";
  const cw = cv.containers.main.clientWidth;
  const ch = cv.containers.main.clientHeight;
  let left = point.x + 14;
  let top = point.y + 14;
  if (left + (el.offsetWidth || 0) > cw - 4) {
    left = point.x - (el.offsetWidth || 0) - 10;
  }
  if (top + (el.offsetHeight || 0) > ch - 4) {
    top = point.y - (el.offsetHeight || 0) - 10;
  }
  el.style.left = left + "px";
  el.style.top = top + "px";
}

function showTradeTooltip(cv, trade, point) {
  const isBull = trade.direction === "bullish";
  const resolved = trade.exit_time !== null && trade.result !== null;
  const row = (label, value) =>
    '<div><span style="color:#94a3b8">' + label + "</span> " + value + "</div>";
  showTooltip(
    cv,
    '<div style="font-weight:700;color:#e94560;margin-bottom:4px">' +
      (isBull ? "LONG" : "SHORT") +
      (trade.source ? " \u00b7 " + trade.source : "") +
      "</div>" +
      row("Entry", trade.entry.toFixed(2)) +
      row("Stop", trade.stop.toFixed(2)) +
      row("Target", trade.target.toFixed(2)) +
      row("R:R", (trade.rr_ratio || 0).toFixed(2)) +
      row("Risk", "$" + (trade.risk_amount || 0).toFixed(2)) +
      row("Win", "$" + ((trade.rr_ratio || 0) * (trade.risk_amount || 0)).toFixed(2)) +
      (resolved
        ? '<div style="margin-top:4px;color:' +
          (trade.result === "win" ? "#22c55e" : "#ef4444") +
          '">' +
          trade.result.toUpperCase() +
          " " +
          (trade.pnl >= 0 ? "+" : "-") +
          "$" +
          Math.abs(trade.pnl).toFixed(2) +
          "</div>"
        : ""),
    point,
  );
}

function hideTradeTooltip(cv) {
  if (cv._tooltipEl) cv._tooltipEl.style.display = "none";
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    onCrosshairMove,
    hitAnnotationTooltip,
    frameAtTime,
    ensureTooltipEl,
    showTooltip,
    showTradeTooltip,
    hideTradeTooltip,
  };
} else if (typeof window !== "undefined") {
  window._mav = window._mav || {};
  window._mav.crosshair = {
    onCrosshairMove,
    hitAnnotationTooltip,
    frameAtTime,
    ensureTooltipEl,
    showTooltip,
    showTradeTooltip,
    hideTradeTooltip,
  };
}
