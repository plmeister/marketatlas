from datetime import datetime, timedelta

import pytest
from marketatlas.data.types import Candle
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.primitive import EMAFact
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.frames.store import FrameStore


def _make_candle(offset: int = 0) -> Candle:
    ts = datetime(2024, 1, 1) + timedelta(hours=offset)
    base = 100.0 + offset
    return Candle(
        timestamp=ts, open=base, high=base + 5,
        low=base - 5, close=base + 2, volume=1000.0,
    )


def _make_frame(offset: int = 0) -> AnalysisFrame:
    candle = _make_candle(offset)
    ema = EMAFact(
        timestamp=candle.timestamp,
        evidence=(
            EvidenceEntry(
                text="EMA signal bullish",
                level=EvidenceLevel.SIGNAL,
                source="EMAAnalyzer",
            ),
        ),
        value=102.0, period=20,
    )
    return AnalysisFrame(
        timestamp=candle.timestamp,
        candle=candle,
        facts={(EMAFact, "ema_20"): ema},
        evidence=(
            EvidenceEntry(
                text="price above EMA",
                level=EvidenceLevel.INFO,
                source="EMAAnalyzer",
            ),
        ),
        annotations=("mark_ema_cross",),
        diagnostics=("debug info",),
    )


class TestAnalysisFrame:
    def test_frozen(self) -> None:
        frame = _make_frame()
        with pytest.raises(AttributeError):
            frame.timestamp = datetime(2025, 1, 1)  # type: ignore[misc]

    def test_default_annotations(self) -> None:
        candle = _make_candle()
        ema = EMAFact(
            timestamp=candle.timestamp, evidence=(), value=100.0, period=20,
        )
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={(EMAFact, "ema_20"): ema},
            evidence=(),
        )
        assert frame.annotations == ()
        assert frame.diagnostics == ()


class TestFrameStore:
    def test_empty(self) -> None:
        store = FrameStore()
        assert len(store) == 0

    def test_append(self) -> None:
        store = FrameStore()
        store.append(_make_frame(0))
        store.append(_make_frame(1))
        assert len(store) == 2

    def test_getitem(self) -> None:
        store = FrameStore()
        for i in range(10):
            store.append(_make_frame(i))
        assert store[5].timestamp == datetime(2024, 1, 1) + timedelta(hours=5)

    def test_slice(self) -> None:
        store = FrameStore()
        for i in range(10):
            store.append(_make_frame(i))
        sliced = store.slice(2, 5)
        assert len(sliced) == 3
        assert sliced[0].timestamp == datetime(2024, 1, 1) + timedelta(hours=2)

    def test_by_timestamp_found(self) -> None:
        store = FrameStore()
        for i in range(5):
            store.append(_make_frame(i))
        target = datetime(2024, 1, 1) + timedelta(hours=3)
        result = store.by_timestamp(target)
        assert result is not None
        assert result.timestamp == target

    def test_by_timestamp_missing(self) -> None:
        store = FrameStore()
        store.append(_make_frame(0))
        result = store.by_timestamp(datetime(2025, 6, 1))
        assert result is None


class TestFrameStoreParquet:
    def test_roundtrip(self, tmp_path: object) -> None:
        path = tmp_path / "frames.parquet"  # type: ignore[operator]
        store = FrameStore()
        for i in range(5):
            store.append(_make_frame(i))
        store.to_parquet(path)  # type: ignore[arg-type]

        loaded = FrameStore.from_parquet(path)  # type: ignore[arg-type]
        assert len(loaded) == 5
        assert loaded[0].timestamp == store[0].timestamp
        assert loaded[4].candle.close == store[4].candle.close

    def test_evidence_preserved(self, tmp_path: object) -> None:
        path = tmp_path / "ev.parquet"  # type: ignore[operator]
        store = FrameStore()
        store.append(_make_frame(0))
        store.to_parquet(path)  # type: ignore[arg-type]

        loaded = FrameStore.from_parquet(path)  # type: ignore[arg-type]
        assert len(loaded[0].evidence) == 1
        assert loaded[0].evidence[0].text == "price above EMA"
        assert loaded[0].evidence[0].level == EvidenceLevel.INFO
        assert loaded[0].annotations == ("mark_ema_cross",)
        assert loaded[0].diagnostics == ("debug info",)
