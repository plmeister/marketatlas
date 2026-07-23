from marketatlas.evidence.collector import EvidenceCollector
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel


class TestEvidenceEntry:
    def test_frozen(self) -> None:
        entry = EvidenceEntry(text="test")
        assert entry.text == "test"
        assert entry.level == EvidenceLevel.INFO
        assert entry.source == ""
        assert entry.annotation_hint == ""

    def test_custom_fields(self) -> None:
        entry = EvidenceEntry(
            text="signal detected",
            level=EvidenceLevel.SIGNAL,
            source="EMAAnalyzer",
            annotation_hint="mark_ema_cross",
        )
        assert entry.level == EvidenceLevel.SIGNAL
        assert entry.source == "EMAAnalyzer"
        assert entry.annotation_hint == "mark_ema_cross"

    def test_equality(self) -> None:
        a = EvidenceEntry(text="x", level=EvidenceLevel.INFO)
        b = EvidenceEntry(text="x", level=EvidenceLevel.INFO)
        assert a == b

    def test_inequality(self) -> None:
        a = EvidenceEntry(text="x", level=EvidenceLevel.INFO)
        b = EvidenceEntry(text="x", level=EvidenceLevel.WARNING)
        assert a != b


class TestEvidenceLevel:
    def test_values(self) -> None:
        assert EvidenceLevel.INFO.value == "info"
        assert EvidenceLevel.SIGNAL.value == "signal"
        assert EvidenceLevel.WARNING.value == "warning"

    def test_from_value(self) -> None:
        assert EvidenceLevel("info") == EvidenceLevel.INFO
        assert EvidenceLevel("signal") == EvidenceLevel.SIGNAL
        assert EvidenceLevel("warning") == EvidenceLevel.WARNING


class TestEvidenceCollector:
    def test_empty_collector(self) -> None:
        collector = EvidenceCollector()
        assert collector.entries() == ()

    def test_add_single(self) -> None:
        collector = EvidenceCollector()
        collector.add("test message")
        entries = collector.entries()
        assert len(entries) == 1
        assert entries[0].text == "test message"
        assert entries[0].level == EvidenceLevel.INFO

    def test_add_with_level(self) -> None:
        collector = EvidenceCollector()
        collector.add("signal", level=EvidenceLevel.SIGNAL, source="TestAnalyzer")
        entries = collector.entries()
        assert entries[0].level == EvidenceLevel.SIGNAL
        assert entries[0].source == "TestAnalyzer"

    def test_add_with_annotation_hint(self) -> None:
        collector = EvidenceCollector()
        collector.add("pullback", annotation_hint="mark_pullback_start")
        entries = collector.entries()
        assert entries[0].annotation_hint == "mark_pullback_start"

    def test_multiple_entries(self) -> None:
        collector = EvidenceCollector()
        collector.add("first")
        collector.add("second")
        collector.add("third")
        assert len(collector.entries()) == 3
        assert collector.entries()[0].text == "first"
        assert collector.entries()[2].text == "third"

    def test_entries_returns_tuple(self) -> None:
        collector = EvidenceCollector()
        collector.add("test")
        result = collector.entries()
        assert isinstance(result, tuple)
        assert len(result) == 1

    def test_by_level_filters_info(self) -> None:
        collector = EvidenceCollector()
        collector.add("info msg", level=EvidenceLevel.INFO)
        collector.add("signal msg", level=EvidenceLevel.SIGNAL)
        collector.add("warning msg", level=EvidenceLevel.WARNING)
        collector.add("another info", level=EvidenceLevel.INFO)
        info_entries = collector.by_level(EvidenceLevel.INFO)
        assert len(info_entries) == 2
        assert all(e.level == EvidenceLevel.INFO for e in info_entries)

    def test_by_level_filters_signal(self) -> None:
        collector = EvidenceCollector()
        collector.add("info", level=EvidenceLevel.INFO)
        collector.add("signal1", level=EvidenceLevel.SIGNAL)
        collector.add("signal2", level=EvidenceLevel.SIGNAL)
        signal_entries = collector.by_level(EvidenceLevel.SIGNAL)
        assert len(signal_entries) == 2

    def test_by_level_filters_warning(self) -> None:
        collector = EvidenceCollector()
        collector.add("info", level=EvidenceLevel.INFO)
        collector.add("warning", level=EvidenceLevel.WARNING)
        warning_entries = collector.by_level(EvidenceLevel.WARNING)
        assert len(warning_entries) == 1
        assert warning_entries[0].text == "warning"

    def test_by_level_empty_when_none_match(self) -> None:
        collector = EvidenceCollector()
        collector.add("info", level=EvidenceLevel.INFO)
        assert collector.by_level(EvidenceLevel.WARNING) == ()

    def test_summary_basic(self) -> None:
        collector = EvidenceCollector()
        collector.add("EMA20 = 103.0")
        summary = collector.summary()
        assert "EMA20 = 103.0" in summary

    def test_summary_with_levels(self) -> None:
        collector = EvidenceCollector()
        collector.add("info message", level=EvidenceLevel.INFO)
        collector.add("signal detected", level=EvidenceLevel.SIGNAL)
        collector.add("warning!", level=EvidenceLevel.WARNING)
        summary = collector.summary()
        assert "info message" in summary
        assert "[SIGNAL] signal detected" in summary
        assert "[WARNING] warning!" in summary

    def test_summary_with_source(self) -> None:
        collector = EvidenceCollector()
        collector.add("value computed", source="EMAAnalyzer")
        summary = collector.summary()
        assert "(EMAAnalyzer)" in summary
        assert "value computed" in summary

    def test_summary_empty(self) -> None:
        collector = EvidenceCollector()
        assert collector.summary() == ""

    def test_immutable_entries(self) -> None:
        collector = EvidenceCollector()
        collector.add("test")
        entries = collector.entries()
        assert isinstance(entries, tuple)
