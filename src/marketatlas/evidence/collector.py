from .model import EvidenceEntry, EvidenceLevel


class EvidenceCollector:
    def __init__(self) -> None:
        self._entries: list[EvidenceEntry] = []

    def add(
        self,
        text: str,
        level: EvidenceLevel = EvidenceLevel.INFO,
        source: str = "",
        annotation_hint: str = "",
    ) -> None:
        self._entries.append(
            EvidenceEntry(text=text, level=level, source=source, annotation_hint=annotation_hint)
        )

    def entries(self) -> tuple[EvidenceEntry, ...]:
        return tuple(self._entries)

    def by_level(self, level: EvidenceLevel) -> tuple[EvidenceEntry, ...]:
        return tuple(e for e in self._entries if e.level == level)

    def summary(self) -> str:
        lines: list[str] = []
        for entry in self._entries:
            prefix = f"[{entry.level.value.upper()}]" if entry.level != EvidenceLevel.INFO else ""
            source = f" ({entry.source})" if entry.source else ""
            lines.append(f"{prefix}{source} {entry.text}".strip())
        return "\n".join(lines)
