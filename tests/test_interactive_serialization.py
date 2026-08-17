from datetime import UTC, datetime, timedelta

from marketatlas.data.types import Candle
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.facts.structural import TrendDirection
from marketatlas.strategy.signals import TradeSignal
from marketatlas.visualization.interactive import _extract_frames_json


BASE = datetime(2024, 6, 1, tzinfo=UTC)


def _make_frame(
    days: int = 0,
    signals: tuple[TradeSignal, ...] = (),
    signal_rejections: tuple[EvidenceEntry, ...] = (),
) -> AnalysisFrame:
    ts = BASE + timedelta(days=days)
    candle = Candle(
        timestamp=ts,
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1000.0,
    )
    return AnalysisFrame(
        timestamp=ts,
        candle=candle,
        facts={},
        evidence=(),
        signals=signals,
        signal_rejections=signal_rejections,
    )


class TestExtractFramesJsonSignalRejections:
    def test_signal_rejections_serialized(self):
        rejection = EvidenceEntry(
            text="Strength 0.12 below threshold 0.3",
            level=EvidenceLevel.WARNING,
            source="PullbackSignal",
        )
        frame = _make_frame(signal_rejections=(rejection,))
        result = _extract_frames_json([frame])

        assert len(result) == 1
        sr = result[0]["signal_rejections"]
        assert len(sr) == 1
        assert sr[0]["text"] == "Strength 0.12 below threshold 0.3"
        assert sr[0]["level"] == "warning"
        assert sr[0]["source"] == "PullbackSignal"

    def test_empty_rejections(self):
        frame = _make_frame()
        result = _extract_frames_json([frame])
        assert result[0]["signal_rejections"] == []

    def test_coexists_with_signals(self):
        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            confidence=0.8,
            source="PullbackSignal",
            entry_zone=(100.0, 105.0),
            evidence=(),
        )
        rejection = EvidenceEntry(
            text="Weak pullback",
            level=EvidenceLevel.WARNING,
            source="PullbackSignal",
        )
        frame = _make_frame(signals=(signal,), signal_rejections=(rejection,))
        result = _extract_frames_json([frame])

        assert len(result[0]["signals"]) == 1
        assert result[0]["signals"][0]["direction"] == "bullish"
        assert len(result[0]["signal_rejections"]) == 1
        assert result[0]["signal_rejections"][0]["text"] == "Weak pullback"
