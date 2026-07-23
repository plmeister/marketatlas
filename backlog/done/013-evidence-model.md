# Evidence Model

**Epic:** mvp

## Problem

Facts carry raw evidence strings, but there's no structured evidence model. Need a way to attach human-readable, visually annotatable context to every analysis result.

## Goal

`Evidence` type with structured entries. Attached to `AnalysisFrame`. Supports different evidence levels and annotation hints.

## Design

### 1. EvidenceEntry

File: `src/marketatlas/evidence/model.py`

```python
class EvidenceLevel(Enum):
    INFO = "info"
    SIGNAL = "signal"
    WARNING = "warning"

@dataclass(frozen=True)
class EvidenceEntry:
    text: str
    level: EvidenceLevel = EvidenceLevel.INFO
    source: str = ""  # which analyzer produced this
    annotation_hint: str = ""  # for visualization (e.g., "mark_pullback_start")
```

### 2. EvidenceCollector

File: `src/marketatlas/evidence/collector.py`

```python
class EvidenceCollector:
    def __init__(self) -> None: ...

    def add(self, text: str, level: EvidenceLevel = ..., source: str = ..., annotation_hint: str = ...) -> None: ...

    def entries(self) -> tuple[EvidenceEntry, ...]: ...

    def summary(self) -> str: ...

    def by_level(self, level: EvidenceLevel) -> tuple[EvidenceEntry, ...]: ...
```

### 3. Integration

- Each `Analyzer` returns `AnalysisResult` with evidence strings
- `EvidenceCollector` aggregates during frame construction
- `AnalysisFrame.evidence` becomes `tuple[EvidenceEntry, ...]` instead of `tuple[str, ...]`
- Update `AnalysisFrame` from backlog 011 to use `EvidenceEntry`

### 4. Tests

- `EvidenceCollector` aggregates entries from multiple analyzers
- `by_level(EvidenceLevel.SIGNAL)` filters correctly
- `summary()` produces human-readable text
- Entries are frozen/immutable

## Evidence

- `EvidenceCollector` produces structured, filterable evidence
- `AnalysisFrame` carries rich evidence for visualization
