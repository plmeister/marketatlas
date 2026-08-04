"""Backlog 065: data requirements inference.

Before execution, derive exactly which ``(instrument, timeframe)`` market data
a run needs: the ``Analysis`` declares timeframes (backlog 061), the runtime
supplies the instrument list (backlog 063), and ``required_data`` produces the
deduplicated, deterministically-ordered pair set — each carrying the date
range so the caller can check persistent-store coverage (backlog 066) before
fetching. ``ensure_required_data`` closes only the coverage gaps.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.instrument import TemplateGraph
from marketatlas.analysis.ast.models import Analysis
from marketatlas.analysis.ast.parser import parse
from marketatlas.analysis.ast.requirements import (
    DataRequirement,
    ensure_required_data,
    required_data,
    required_timeframes,
)
from marketatlas.data.datastore import DataStore
from marketatlas.data.instrument import Instrument
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe

D = Timeframe.D1
W = Timeframe.W1

START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2024, 6, 1, tzinfo=UTC)

_TF_STRATEGY = """
tf1d := timeframe { resolution: "1d" }
tf1w := timeframe { resolution: "1w" }
ema := ema { timeframe: tf1d, period: 20 }
swings := swingstructure { timeframe: tf1w, lookback: 5 }
"""


def _instrument(canonical: str, description: str | None = None) -> Instrument:
    return Instrument(
        canonical=canonical,
        asset_class="forex",
        description=description or f"{canonical} pair",
        providers={"yahoo": canonical},
    )


def _multi_tf_analysis() -> Analysis:
    return parse(_TF_STRATEGY, name="strategy")


class TestRequiredTimeframes:
    def test_empty_analysis(self) -> None:
        assert required_timeframes(Analysis(name="a", version="1.0")) == ()

    def test_no_tf_defs_empty(self) -> None:
        a = parse("ema := ema { period: 20 }", name="a")
        assert required_timeframes(a) == ()

    def test_single_tf(self) -> None:
        a = parse('tf1h := timeframe { resolution: "1h" }\nema := ema { period: 20 }', name="a")
        assert required_timeframes(a) == (Timeframe.H1,)

    def test_declaration_order(self) -> None:
        a = _multi_tf_analysis()
        assert required_timeframes(a) == (D, W)

    def test_dedup(self) -> None:
        a = parse(
            'tf1d := timeframe { resolution: "1d" }\n'
            'tf_again := timeframe { resolution: "1d" }\n'
            "ema := ema { period: 20 }",
            name="a",
        )
        assert required_timeframes(a) == (D,)

    def test_invalid_value_skipped(self) -> None:
        a = Analysis(name="a", version="1.0", timeframes=("13m", "1d"))
        assert required_timeframes(a) == (D,)

    def test_method_matches_function(self) -> None:
        a = _multi_tf_analysis()
        assert a.required_timeframes() == required_timeframes(a)


class TestRequiredData:
    def test_single_instrument_single_tf(self) -> None:
        a = parse('tf1h := timeframe { resolution: "1h" }\nema := ema { period: 20 }', name="a")
        reqs = required_data(a, [_instrument("EURUSD")], START, END)
        assert reqs == (DataRequirement(_instrument("EURUSD"), Timeframe.H1, START, END),)

    def test_multi_tf_per_instrument(self) -> None:
        reqs = required_data(_multi_tf_analysis(), [_instrument("EURUSD")], START, END)
        assert [(r.instrument.canonical, r.timeframe) for r in reqs] == [
            ("EURUSD", D),
            ("EURUSD", W),
        ]

    def test_multi_instrument_product(self) -> None:
        instruments = [_instrument("EURUSD"), _instrument("GBPUSD")]
        reqs = required_data(_multi_tf_analysis(), instruments, START, END)
        assert [(r.instrument.canonical, r.timeframe) for r in reqs] == [
            ("EURUSD", D),
            ("EURUSD", W),
            ("GBPUSD", D),
            ("GBPUSD", W),
        ]

    def test_duplicate_instruments_deduped_by_canonical(self) -> None:
        first = _instrument("EURUSD", description="primary")
        duplicate = _instrument("EURUSD", description="duplicate listing")
        reqs = required_data(_multi_tf_analysis(), [first, duplicate], START, END)
        assert [r.instrument.canonical for r in reqs] == ["EURUSD", "EURUSD"]
        assert all(r.instrument is first for r in reqs)

    def test_deterministic(self) -> None:
        instruments = [_instrument("GBPUSD"), _instrument("EURUSD")]
        a = required_data(_multi_tf_analysis(), instruments, START, END)
        b = required_data(_multi_tf_analysis(), instruments, START, END)
        assert a == b

    def test_empty_instruments_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one instrument"):
            required_data(_multi_tf_analysis(), [], START, END)

    def test_no_timeframes_empty(self) -> None:
        a = parse("ema := ema { period: 20 }", name="a")
        assert required_data(a, [_instrument("EURUSD")], START, END) == ()

    def test_date_range_carried(self) -> None:
        reqs = required_data(_multi_tf_analysis(), [_instrument("EURUSD")], START, END)
        assert all(r.start == START and r.end == END for r in reqs)


class TestTemplateGraphRequirements:
    def _template(self, source: str) -> TemplateGraph:
        return ASTCompiler.compile_template(parse(source, name="strategy"))

    def test_default_base_timeframe(self) -> None:
        template = self._template("ema := ema { period: 20 }")
        assert template.required_timeframes() == (D,)

    def test_declared_timeframes(self) -> None:
        template = self._template(_TF_STRATEGY)
        assert template.required_timeframes() == (D, W)

    def test_required_data_product(self) -> None:
        template = self._template(_TF_STRATEGY)
        reqs = template.required_data([_instrument("EURUSD"), _instrument("GBPUSD")], START, END)
        assert [(r.instrument.canonical, r.timeframe) for r in reqs] == [
            ("EURUSD", D),
            ("EURUSD", W),
            ("GBPUSD", D),
            ("GBPUSD", W),
        ]
        assert all(isinstance(r, DataRequirement) for r in reqs)

    def test_required_data_empty_instruments_raises(self) -> None:
        template = self._template(_TF_STRATEGY)
        with pytest.raises(ValueError, match="At least one instrument"):
            template.required_data([], START, END)

    def test_config_timeframes_drive_template(self) -> None:
        template = self._template(_TF_STRATEGY)
        expected = tuple(Timeframe(v) for v in template.config.timeframes)
        assert template.required_timeframes() == expected


class TestEnsureRequiredData:
    def _provider(self) -> FakeProvider:
        return FakeProvider()

    def test_fetches_every_requirement_once(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = DataStore(tmp_path)
        provider = self._provider()
        reqs = required_data(_multi_tf_analysis(), [_instrument("EURUSD")], START, END)
        out = ensure_required_data(
            store, reqs, provider, resolve_symbol=lambda i: Symbol(i.canonical)
        )
        assert len(out) == 2
        assert [md.timeframe for md in out] == [D, W]
        assert [(s.name, tf) for s, tf, _, _ in provider.calls] == [
            ("EURUSD", D),
            ("EURUSD", W),
        ]

    def test_cached_range_not_refetched(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = DataStore(tmp_path)
        provider = self._provider()
        analysis = parse(
            'tf1h := timeframe { resolution: "1h" }\nema := ema { period: 20 }', name="a"
        )
        reqs = required_data(analysis, [_instrument("EURUSD")], START, END)
        ensure_required_data(store, reqs, provider, resolve_symbol=lambda i: Symbol(i.canonical))
        calls_after_first = len(provider.calls)

        ensure_required_data(store, reqs, provider, resolve_symbol=lambda i: Symbol(i.canonical))
        assert len(provider.calls) == calls_after_first

    def test_partial_gap_fetches_only_missing(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = DataStore(tmp_path)
        provider = self._provider()
        reqs = required_data(_multi_tf_analysis(), [_instrument("EURUSD")], START, END)
        ensure_required_data(store, reqs, provider, resolve_symbol=lambda i: Symbol(i.canonical))

        later_start = END + timedelta(days=1)
        later_end = END + timedelta(days=30)
        later_reqs = required_data(
            _multi_tf_analysis(), [_instrument("EURUSD")], later_start, later_end
        )
        before = len(provider.calls)
        ensure_required_data(
            store, later_reqs, provider, resolve_symbol=lambda i: Symbol(i.canonical)
        )
        # Two ranges already cached; only the leading gap is fetched per timeframe.
        assert len(provider.calls) == before + 2


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[Symbol, Timeframe, datetime, datetime]] = []

    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData:
        self.calls.append((symbol, timeframe, start, end))
        candles = []
        current = start
        step = timedelta(days=1) if timeframe.value not in ("1w",) else timedelta(weeks=1)
        while current <= end:
            candles.append(
                Candle(
                    timestamp=current,
                    open=100.0,
                    high=110.0,
                    low=95.0,
                    close=105.0,
                    volume=5000.0,
                )
            )
            current += step
        return MarketData(symbol=symbol, timeframe=timeframe, candles=tuple(candles))
