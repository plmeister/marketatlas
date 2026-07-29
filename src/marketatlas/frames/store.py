from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from marketatlas.data.types import Candle
from marketatlas.evidence.model import EvidenceEntry

from .frame import AnalysisFrame


def _serialize_evidence(entries: tuple[EvidenceEntry, ...]) -> str:
    items = [
        {
            "text": e.text,
            "level": e.level.value,
            "source": e.source,
            "annotation_hint": e.annotation_hint,
        }
        for e in entries
    ]
    return json.dumps(items)


def _deserialize_evidence(raw: str) -> tuple[EvidenceEntry, ...]:
    from marketatlas.evidence.model import EvidenceLevel

    items = json.loads(raw)
    return tuple(
        EvidenceEntry(
            text=item["text"],
            level=EvidenceLevel(item["level"]),
            source=item.get("source", ""),
            annotation_hint=item.get("annotation_hint", ""),
        )
        for item in items
    )


class FrameStore:
    def __init__(self) -> None:
        self._frames: list[AnalysisFrame] = []

    def append(self, frame: AnalysisFrame) -> None:
        self._frames.append(frame)

    def __len__(self) -> int:
        return len(self._frames)

    def __getitem__(self, index: int) -> AnalysisFrame:
        return self._frames[index]

    def __iter__(self) -> Iterator[AnalysisFrame]:
        return iter(self._frames)

    def slice(self, start: int, end: int) -> list[AnalysisFrame]:
        return self._frames[start:end]

    def by_timestamp(self, ts: datetime) -> AnalysisFrame | None:
        for frame in self._frames:
            if frame.timestamp == ts:
                return frame
        return None

    def to_parquet(self, path: Path) -> None:
        rows: list[dict[str, Any]] = []
        for f in self._frames:
            facts_dict: dict[str, Any] = {}
            for fact_key, fact in f.facts.items():
                raw: dict[str, Any] = {"key": fact_key.name}
                for k, v in fact.__dict__.items():
                    if isinstance(v, datetime):
                        raw[k] = v.isoformat()
                    elif isinstance(v, tuple) and v and isinstance(v[0], EvidenceEntry):
                        raw[k] = _serialize_evidence(v)
                    else:
                        raw[k] = v
                facts_dict[fact_key.name] = raw
            rows.append(
                {
                    "timestamp": f.timestamp.isoformat(),
                    "open": f.candle.open,
                    "high": f.candle.high,
                    "low": f.candle.low,
                    "close": f.candle.close,
                    "volume": f.candle.volume,
                    "facts": json.dumps(facts_dict),
                    "evidence": _serialize_evidence(f.evidence),
                    "annotations": json.dumps(f.annotations),
                    "diagnostics": json.dumps(f.diagnostics),
                }
            )
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, path)

    @classmethod
    def from_parquet(cls, path: Path) -> FrameStore:
        table = pq.read_table(path)
        rows = table.to_pydict()
        store = cls()
        n = len(rows["timestamp"])
        for i in range(n):
            facts_raw: dict[str, Any] = json.loads(rows["facts"][i])
            # facts reconstructed as plain dicts; actual Fact objects require type registry
            store.append(
                AnalysisFrame(
                    timestamp=datetime.fromisoformat(rows["timestamp"][i]),
                    candle=Candle(
                        timestamp=datetime.fromisoformat(rows["timestamp"][i]),
                        open=rows["open"][i],
                        high=rows["high"][i],
                        low=rows["low"][i],
                        close=rows["close"][i],
                        volume=rows["volume"][i],
                    ),
                    facts=facts_raw,  # type: ignore[arg-type]
                    evidence=_deserialize_evidence(rows["evidence"][i]),
                    annotations=tuple(json.loads(rows["annotations"][i])),
                    diagnostics=tuple(json.loads(rows["diagnostics"][i])),
                )
            )
        return store
