from datetime import UTC, datetime

import pytest

from marketatlas.facts import (
    ATRFact,
    EMAFact,
    Fact,
    PullbackFact,
    PullbackStatus,
    RSIFact,
    SMAFact,
    TrendDirection,
    TrendFact,
    VolumeFact,
)

TS = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
EVIDENCE = ("EMA20 = 50234.52", "above price")


class TestBaseFact:
    def test_construction(self) -> None:
        f = Fact(timestamp=TS, evidence=EVIDENCE)
        assert f.timestamp == TS
        assert f.evidence == EVIDENCE

    def test_frozen(self) -> None:
        f = Fact(timestamp=TS, evidence=EVIDENCE)
        with pytest.raises(AttributeError):
            f.timestamp = TS  # type: ignore[misc]

    def test_evidence_required(self) -> None:
        f = Fact(timestamp=TS, evidence=())
        assert f.evidence == ()


class TestEMAFact:
    def test_construction(self) -> None:
        f = EMAFact(timestamp=TS, evidence=EVIDENCE, value=50000.0, period=20)
        assert f.value == 50000.0
        assert f.period == 20
        assert f.timestamp == TS

    def test_frozen(self) -> None:
        f = EMAFact(timestamp=TS, evidence=EVIDENCE, value=50000.0, period=20)
        with pytest.raises(AttributeError):
            f.value = 51000.0  # type: ignore[misc]


class TestSMAFact:
    def test_construction(self) -> None:
        f = SMAFact(timestamp=TS, evidence=(), value=49500.0, period=50)
        assert f.value == 49500.0
        assert f.period == 50


class TestATRFact:
    def test_construction(self) -> None:
        f = ATRFact(timestamp=TS, evidence=(), value=1234.56, period=14)
        assert f.value == 1234.56
        assert f.period == 14

    def test_frozen(self) -> None:
        f = ATRFact(timestamp=TS, evidence=(), value=1234.56, period=14)
        with pytest.raises(AttributeError):
            f.value = 2000.0  # type: ignore[misc]


class TestRSIFact:
    def test_construction(self) -> None:
        f = RSIFact(timestamp=TS, evidence=(), value=65.3, period=14)
        assert f.value == 65.3
        assert f.period == 14


class TestVolumeFact:
    def test_construction(self) -> None:
        f = VolumeFact(timestamp=TS, evidence=(), avg_volume=1500000.0, period=20)
        assert f.avg_volume == 1500000.0
        assert f.period == 20


class TestTrendFact:
    def test_construction(self) -> None:
        f = TrendFact(
            timestamp=TS,
            evidence=(),
            direction=TrendDirection.BULLISH,
            strength=0.72,
        )
        assert f.direction == TrendDirection.BULLISH
        assert f.strength == 0.72

    def test_enum_values(self) -> None:
        assert TrendDirection.BULLISH.value == "bullish"
        assert TrendDirection.BEARISH.value == "bearish"
        assert TrendDirection.NEUTRAL.value == "neutral"

    def test_frozen(self) -> None:
        f = TrendFact(
            timestamp=TS, evidence=(), direction=TrendDirection.BEARISH, strength=0.5
        )
        with pytest.raises(AttributeError):
            f.direction = TrendDirection.NEUTRAL  # type: ignore[misc]


class TestPullbackFact:
    def test_construction(self) -> None:
        f = PullbackFact(
            timestamp=TS,
            evidence=(),
            status=PullbackStatus.DETECTED,
            retracement_atr=1.2,
            direction=TrendDirection.BULLISH,
        )
        assert f.status == PullbackStatus.DETECTED
        assert f.retracement_atr == 1.2
        assert f.direction == TrendDirection.BULLISH

    def test_status_enum_values(self) -> None:
        assert PullbackStatus.DETECTED.value == "detected"
        assert PullbackStatus.CONFIRMED.value == "confirmed"
        assert PullbackStatus.INVALIDATED.value == "invalidated"

    def test_frozen(self) -> None:
        f = PullbackFact(
            timestamp=TS,
            evidence=(),
            status=PullbackStatus.DETECTED,
            retracement_atr=1.0,
            direction=TrendDirection.BULLISH,
        )
        with pytest.raises(AttributeError):
            f.status = PullbackStatus.CONFIRMED  # type: ignore[misc]


class TestFactInheritance:
    def test_emafact_is_fact(self) -> None:
        f = EMAFact(timestamp=TS, evidence=(), value=50000.0, period=20)
        assert isinstance(f, Fact)

    def test_trendfact_is_fact(self) -> None:
        f = TrendFact(
            timestamp=TS, evidence=(), direction=TrendDirection.BULLISH, strength=0.8
        )
        assert isinstance(f, Fact)

    def test_pullbackfact_is_fact(self) -> None:
        f = PullbackFact(
            timestamp=TS,
            evidence=(),
            status=PullbackStatus.DETECTED,
            retracement_atr=1.0,
            direction=TrendDirection.BULLISH,
        )
        assert isinstance(f, Fact)
