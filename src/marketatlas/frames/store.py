from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from marketatlas.data.types import Candle

from .frame import AnalysisFrame


class FrameStore:
    def __init__(self) -> None:
        self._frames: list[AnalysisFrame] = []

    def append(self, frame: AnalysisFrame) -> None:
        self._frames.append(frame)

    def __len__(self) -> int:
        return len(self._frames)

    def __getitem__(self, index: int) -> AnalysisFrame:
        return self._frames[index]

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
            for fact_type, fact in f.facts.items():
                raw: dict[str, Any] = {"type": fact_type.__name__}
                for k, v in fact.__dict__.items():
                    raw[k] = v.isoformat() if isinstance(v, datetime) else v
                facts_dict[fact_type.__name__] = raw
            rows.append(
                {
                    "timestamp": f.timestamp.isoformat(),
                    "open": f.candle.open,
                    "high": f.candle.high,
                    "low": f.candle.low,
                    "close": f.candle.close,
                    "volume": f.candle.volume,
                    "facts": json.dumps(facts_dict),
                    "evidence": json.dumps(f.evidence),
                    "annotations": json.dumps(f.annotations),
                    "diagnostics": json.dumps(f.diagnostics),
                }
            )
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, path)  # type: ignore[no-untyped-call]

    @classmethod
    def from_parquet(cls, path: Path) -> FrameStore:
        table = pq.read_table(path)  # type: ignore[no-untyped-call]
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
                    evidence=tuple(json.loads(rows["evidence"][i])),
                    annotations=tuple(json.loads(rows["annotations"][i])),
                    diagnostics=tuple(json.loads(rows["diagnostics"][i])),
                )
            )
        return store
