from __future__ import annotations

import pickle
import re
from pathlib import Path

from marketatlas.analysis.analyzers.swing import SwingStructureAnalyzer
from marketatlas.data.store import MarketStore
from marketatlas.data.view import MarketView
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import SwingFact, SwingPoint, SwingType
from marketatlas.frames.frame import AnalysisFrame


class SwingDebugger:
    def __init__(
        self,
        pkl_path: str | Path,
        min_swing_atr: float | None = None,
        left_bars: int = 2,
        right_bars: int = 1,
        atr_key: str = "atr_14",
    ):
        with open(pkl_path, "rb") as f:
            data = pickle.load(f)
        self.store: MarketStore = data["store"]
        self.frames: list[AnalysisFrame] = data["frames"]
        self.window_size: int = data["window_size"]
        self._min_swing_atr_override = min_swing_atr
        self._left_bars = left_bars
        self._right_bars = right_bars
        self._atr_key = atr_key

    def _cursor(self, frame_idx: int) -> int:
        return self.window_size + frame_idx

    def _atr_value(self, frame_idx: int) -> float:
        for fact in self.frames[frame_idx].facts.values():
            if isinstance(fact, ATRFact):
                return fact.value
        return 0.0

    def _min_swing_atr_from_evidence(self, frame_idx: int) -> float:
        for fact in self.frames[frame_idx].facts.values():
            if isinstance(fact, SwingFact):
                for ev in fact.evidence:
                    m = re.search(r"minimum\s+([\d.]+)\s+ATR", ev.text)
                    if m:
                        return float(m.group(1))
        return 0.3

    def _min_swing_atr(self, frame_idx: int) -> float:
        if self._min_swing_atr_override is not None:
            return self._min_swing_atr_override
        return self._min_swing_atr_from_evidence(frame_idx)

    def _saved_swings(self, frame_idx: int) -> tuple[SwingPoint, ...]:
        for fact in self.frames[frame_idx].facts.values():
            if isinstance(fact, SwingFact):
                return fact.swings
        return ()

    def _fmt_swing(self, s: SwingPoint) -> str:
        return f"{s.index}({s.type.name[:1]}@{s.price:.2f})"

    def _fmt_swings(self, swings: list[SwingPoint]) -> str:
        return " ".join(self._fmt_swing(s) for s in swings)

    def analyze(self, frame_idx: int) -> dict:
        cursor = self._cursor(frame_idx)
        view = MarketView(self.store, cursor, self.window_size)
        atr = self._atr_value(frame_idx)
        min_atr = self._min_swing_atr(frame_idx)
        min_sep = min_atr * atr
        all_candles = tuple(self.store.slice(0, view.cursor)) + (view.current,)
        analyzer = SwingStructureAnalyzer(
            min_swing_atr=min_atr,
            left_bars=self._left_bars,
            right_bars=self._right_bars,
            atr_key=self._atr_key,
        )
        raw = analyzer._find_raw_swings(all_candles, 0, self._left_bars, self._right_bars)
        after_alt1 = analyzer._filter_alternating(raw)
        after_atr = analyzer._filter_atr_separation(after_alt1, atr)
        final = analyzer._filter_alternating(after_atr)
        return {
            "frame_idx": frame_idx,
            "cursor": cursor,
            "atr": atr,
            "min_swing_atr": min_atr,
            "min_sep": min_sep,
            "raw": raw,
            "after_alternating_1": after_alt1,
            "after_atr": after_atr,
            "final": final,
            "saved": list(self._saved_swings(frame_idx)),
            "match": [s.index for s in final] == [s.index for s in self._saved_swings(frame_idx)],
        }

    def trace(self, frame_idx: int) -> str:
        r = self.analyze(frame_idx)
        lines = []
        lines.append(f"Frame {frame_idx}  cursor={r['cursor']}  ATR={r['atr']:.2f}  min_sep={r['min_sep']:.2f}")
        lines.append(f"Total candles: {self._cursor(frame_idx) + 1}")
        lines.append("")
        lines.append(f"RAW ({len(r['raw'])}): {self._fmt_swings(r['raw'])}")
        lines.append("")
        merged = self._find_alternating_detail(r['raw'], r['after_alternating_1'], r['min_sep'])
        if merged:
            lines.append(f"ALTERNATING 1 ({len(r['after_alternating_1'])}): {self._fmt_swings(r['after_alternating_1'])}")
            for line in merged:
                lines.append(f"  {line}")
        else:
            lines.append(f"ALTERNATING 1: no change")
        lines.append("")
        filtered = self._filter_atr_detail(r['after_alternating_1'], r['min_sep'])
        if filtered:
            lines.append(f"ATR FILTER ({len(r['after_atr'])}): {self._fmt_swings(r['after_atr'])}")
            for line in filtered:
                lines.append(f"  {line}")
        else:
            lines.append(f"ATR FILTER: no change")
        lines.append("")
        merged2 = self._find_alternating_detail(r['after_atr'], r['final'], r['min_sep'])
        if merged2:
            lines.append(f"ALTERNATING 2 ({len(r['final'])}): {self._fmt_swings(r['final'])}")
            for line in merged2:
                lines.append(f"  {line}")
        else:
            lines.append(f"ALTERNATING 2: no change")
        lines.append("")
        saved = self._saved_swings(frame_idx)
        lines.append(f"SAVED ({len(saved)}): {self._fmt_swings(list(saved))}")
        if r['match']:
            lines.append("✓ re-run matches saved result")
        else:
            saved_set = {s.index for s in saved}
            rerun_set = {s.index for s in r['final']}
            added = rerun_set - saved_set
            removed = saved_set - rerun_set
            if added:
                lines.append(f"✗ NEW indices in re-run: {sorted(added)}")
            if removed:
                lines.append(f"✗ MISSING indices in re-run: {sorted(removed)}")
        return "\n".join(lines)

    def diff(self, frame_a: int, frame_b: int) -> str:
        ra = self.analyze(frame_a)
        rb = self.analyze(frame_b)
        a_set = {s.index: s for s in ra['final']}
        b_set = {s.index: s for s in rb['final']}
        a_indices = set(a_set.keys())
        b_indices = set(b_set.keys())
        added = b_indices - a_indices
        removed = a_indices - b_indices
        kept = a_indices & b_indices

        lines = []
        lines.append(f"Swing diff: Frame {frame_a} → Frame {frame_b}")
        lines.append(f"  Final count: {len(ra['final'])} → {len(rb['final'])}")
        lines.append("")
        if removed:
            lines.append("  REMOVED:")
            for idx in sorted(removed):
                lines.append(f"    {self._fmt_swing(a_set[idx])}")
        if added:
            lines.append("  ADDED:")
            for idx in sorted(added):
                lines.append(f"    {self._fmt_swing(b_set[idx])}")
        changed = []
        for idx in sorted(kept):
            if a_set[idx].price != b_set[idx].price:
                changed.append((a_set[idx], b_set[idx]))
        if changed:
            lines.append("  PRICE CHANGE:")
            for sa, sb in changed:
                lines.append(f"    {sa.index}: {sa.price:.2f} → {sb.price:.2f}")
        if not added and not removed and not changed:
            lines.append("  (identical)")
        return "\n".join(lines)

    def _find_alternating_detail(self, before: list[SwingPoint], after: list[SwingPoint], _min_sep: float) -> list[str]:
        before_set = {s.index: s for s in before}
        after_set = {s.index: s for s in after}
        removed = [s for s in before if s.index not in after_set]
        if not removed:
            return []
        result = []
        for r in removed:
            merger = None
            for a in after:
                if a.type == r.type:
                    merger = a
                    break
            if merger:
                direction = "higher" if r.type == SwingType.HIGH else "lower"
                result.append(f"merge: {self._fmt_swing(r)} → kept {self._fmt_swing(merger)} ({direction})")
            else:
                result.append(f"merge: {self._fmt_swing(r)} (no replacement found)")
        return result

    def _filter_atr_detail(self, before: list[SwingPoint], min_sep: float) -> list[str]:
        result = []
        last_high_price: float | None = None
        last_low_price: float | None = None
        for s in before:
            if s.type == SwingType.HIGH:
                if last_high_price is not None and abs(s.price - last_high_price) < min_sep:
                    result.append(
                        f"filter: {self._fmt_swing(s)} |{s.price:.2f} - {last_high_price:.2f}| = "
                        f"{abs(s.price - last_high_price):.2f} < {min_sep:.2f}"
                    )
                else:
                    last_high_price = s.price
            else:
                if last_low_price is not None and abs(s.price - last_low_price) < min_sep:
                    result.append(
                        f"filter: {self._fmt_swing(s)} |{s.price:.2f} - {last_low_price:.2f}| = "
                        f"{abs(s.price - last_low_price):.2f} < {min_sep:.2f}"
                    )
                else:
                    last_low_price = s.price
        return result

    def find_unstable_swings(self) -> list[tuple[int, int, str]]:
        unstable: list[tuple[int, int, str]] = []
        for i in range(len(self.frames) - 1):
            a = self.analyze(i)['final']
            b = self.analyze(i + 1)['final']
            a_set = {s.index: s for s in a}
            b_set = {s.index: s for s in b}
            for idx in sorted(set(b_set.keys()) - set(a_set.keys())):
                unstable.append((i, i + 1, f"ADDED {self._fmt_swing(b_set[idx])}"))
            for idx in sorted(set(a_set.keys()) - set(b_set.keys())):
                unstable.append((i, i + 1, f"REMOVED {self._fmt_swing(a_set[idx])}"))
        return unstable
