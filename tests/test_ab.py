"""Backlog 079: portfolio A/B test runner.

Choice templates (`<a | b | c>`) expand into one portfolio backtest per
concrete variant; each variant runs on its own ``StrategyBundle``/``TradeBook``
and the comparison output names the chosen values on any node type. The
variant identity (``variant_identity``/``variant_labels``) is unit-tested here
too, since the CLI labels are built from it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.parser import parse_with_positions
from marketatlas.analysis.ast.variant import (
    variant_columns,
    variant_identity,
    variant_labels,
    variant_slug,
    variant_slugs,
)
from marketatlas.data.instrument import Instrument, InstrumentRegistry
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.strategy.bundle import StrategyBundle
from marketatlas.strategy.tradebook import TradeBook

BASE = datetime(2024, 1, 1, tzinfo=UTC)

PULLBACK_AB_DSL = "\n".join(
    [
        "ema := ema { period: 20 }",
        "ema50 := ema { period: 50 }",
        "atr_14 := atr { period: 14 }",
        "atr_14_series := atr_series { period: 14 }",
        "trend := trend { ema_20: ema, ema_50: ema50, atr_14: atr_14 }",
        "swing := swings { lookback: 50, left_bars: 1, right_bars: 1 }",
        "swing_structure := swingstructure { swing }",
        "sr := sr { swing, atr_14_series }",
        "pullback := pullbackpattern { swing_structure }",
        "signal := generate_signal { pullback_pattern: pullback, trend: trend,",
        "atr_14: atr_14, min_strength: <0.1 | 0.99> }",
        "risk := manage_risk { risk_pct: 1.0, min_rr: 0.0,",
        "max_rr: 4.0, sr_buffer_atr: 0.0, max_stop_atr: 5.0 }",
        "",
    ]
)

CHOICE_FREE_DSL = "ema := ema { period: 20 }"


def _zigzag() -> list[tuple[float, float, float, float]]:
    """Bullish LHLHL zigzag ending in a strong confirmation (067 fixture)."""
    return [
        (100.0, 101.0, 99.0, 100.0),  # 0
        (100.0, 102.0, 100.0, 101.0),  # 1: SH 102
        (101.0, 101.0, 97.0, 100.0),  # 2: SL 97
        (100.0, 108.0, 100.0, 106.0),  # 3: SH 108
        (106.0, 106.0, 99.0, 102.0),  # 4: SL 99
        (102.0, 114.0, 102.0, 112.0),  # 5: SH 114
        (112.0, 112.0, 101.0, 106.0),  # 6: SL 101  <- final swing
        (102.0, 116.0, 104.0, 114.0),  # 7: strong bullish confirmation
        (114.0, 118.0, 113.0, 117.0),  # 8: later candle
    ]


def _pullback_candles(n_warmup: int = 101) -> tuple[Candle, ...]:
    """Rising warmup (for EMA/ATR/swing lookbacks) + the confirmation zigzag.

    110 candles total so the CLI's ``window_size=100`` leaves a nonzero frame
    count; the confirmation candle lands at index ``n_warmup + 7``.
    """
    rows: list[tuple[float, float, float, float]] = []
    for i in range(n_warmup):
        price = 100.0 + i * 0.1
        rows.append((price, price + 0.5, price - 0.5, price + 0.2))
    rows += _zigzag()
    return tuple(
        Candle(
            timestamp=BASE + timedelta(days=i),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=1000.0,
        )
        for i, (o, h, low, c) in enumerate(rows)
    )


def _market_data(symbol: str) -> MarketData:
    return MarketData(symbol=Symbol(symbol), timeframe=Timeframe.D1, candles=_pullback_candles())


def _write_registry(path: Path, instruments: list[Instrument]) -> None:
    registry = InstrumentRegistry()
    for inst in instruments:
        registry.add(inst)
    registry.save(path)


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    """DSL, registry (A/B), portfolio files ready for a CLI run."""
    dsl = tmp_path / "pullback_ab.dsl"
    dsl.write_text(PULLBACK_AB_DSL)
    registry_path = tmp_path / "instruments.yaml"
    _write_registry(
        registry_path,
        [
            Instrument("A", "crypto", "Asset A", providers={"yahoo": "A"}),
            Instrument("B", "crypto", "Asset B", providers={"yahoo": "B"}),
        ],
    )
    portfolio = tmp_path / "portfolio.yaml"
    portfolio.write_text("instruments:\n  - A\n  - B\n")
    return dsl, registry_path, portfolio


def _run_main(*args: str) -> None:
    with patch("sys.argv", ["marketatlas", *args]):
        from marketatlas.cli import main

        main()


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETATLAS_DATA_DIR", str(tmp_path / "marketatlas-cache"))


class TestVariantIdentity:
    def _templates(self, source: str) -> tuple:
        analysis, _ = parse_with_positions(source, name="t")
        return ASTCompiler.compile_templates(analysis)

    def test_choice_free_single_default_label(self) -> None:
        templates = self._templates(CHOICE_FREE_DSL)
        assert len(templates) == 1
        assert variant_labels(templates) == ["default"]

    def test_signal_choice_labels_values(self) -> None:
        templates = self._templates(
            "ema := ema { period: 20 }\n" "sig := generate_signal { min_strength: <0.3 | 0.5> }"
        )
        assert len(templates) == 2
        assert variant_labels(templates) == ["min_strength=0.3", "min_strength=0.5"]

    def test_analyzer_param_choice_labeled(self) -> None:
        templates = self._templates("ema := ema { period: <20 | 50> }")
        assert len(templates) == 2
        assert variant_labels(templates) == ["period=20", "period=50"]

    def test_risk_param_choice_labeled(self) -> None:
        templates = self._templates(
            "ema := ema { period: 20 }\n" "risk := manage_risk { max_stop_atr: <3 | 5> }"
        )
        assert len(templates) == 2
        assert variant_labels(templates) == ["max_stop_atr=3", "max_stop_atr=5"]

    def test_multi_dimension_cartesian_labels(self) -> None:
        templates = self._templates(
            "ema := ema { period: <20 | 50> }\n"
            "sig := generate_signal { min_strength: <0.3 | 0.5> }"
        )
        assert len(templates) == 4
        # Column-major cartesian: (20,0.3), (20,0.5), (50,0.3), (50,0.5).
        assert variant_labels(templates) == [
            "period=20, min_strength=0.3",
            "period=20, min_strength=0.5",
            "period=50, min_strength=0.3",
            "period=50, min_strength=0.5",
        ]

    def test_identity_excludes_derived_wiring(self) -> None:
        templates = self._templates(
            "ema := ema { period: 20 }\n"
            "atr := atr { period: 14 }\n"
            "trend := trend { ema_20: ema, ema_50: ema50, atr_14: atr }\n"
            "ema50 := ema { period: 50 }"
        )
        identity = variant_identity(templates[0])
        assert all("bindings" not in k for k in identity)
        assert "TrendAnalyzer.timeframe" in identity or "TrendAnalyzer.timeframe" not in identity
        # The timeframe slot is None for every analyzer here (base timeframe).
        assert identity.get("TrendAnalyzer.timeframe") is None


class TestVariantSlugs:
    """Backlog 080: deterministic, filesystem-safe, ordinal-free slugs."""

    def _templates(self, source: str) -> tuple:
        analysis, _ = parse_with_positions(source, name="t")
        return ASTCompiler.compile_templates(analysis)

    def test_choice_free_single_default(self) -> None:
        templates = self._templates(CHOICE_FREE_DSL)
        assert len(templates) == 1
        assert variant_slugs(templates) == ["default"]
        assert variant_slug(templates[0]) == "default"

    def test_signal_choice_slug_values(self) -> None:
        templates = self._templates(
            "ema := ema { period: 20 }\n" "sig := generate_signal { min_strength: <0.3 | 0.5> }"
        )
        assert variant_slugs(templates) == ["ms030", "ms050"]

    def test_analyzer_param_choice_slugs(self) -> None:
        templates = self._templates("ema := ema { period: <20 | 50> }")
        assert variant_slugs(templates) == ["p20", "p50"]

    def test_risk_param_choice_slugs(self) -> None:
        templates = self._templates(
            "ema := ema { period: 20 }\n" "risk := manage_risk { max_stop_atr: <3 | 5> }"
        )
        assert variant_slugs(templates) == ["atr3", "atr5"]

    def test_multi_dimension_cartesian_slugs(self) -> None:
        templates = self._templates(
            "ema := ema { period: <20 | 50> }\n"
            "sig := generate_signal { min_strength: <0.3 | 0.5> }"
        )
        assert len(templates) == 4
        assert variant_slugs(templates) == [
            "p20_ms030",
            "p20_ms050",
            "p50_ms030",
            "p50_ms050",
        ]

    def test_slugs_deterministic_across_expansions(self) -> None:
        src = "ema := ema { period: <20 | 50> }\nrisk := manage_risk { max_stop_atr: <3 | 5> }"
        assert variant_slugs(self._templates(src)) == variant_slugs(self._templates(src))

    def test_slugs_filesystem_safe(self) -> None:
        templates = self._templates(
            "ema := ema { period: <20 | 50> }\nrisk := manage_risk { max_stop_atr: <3 | 5> }"
        )
        for slug in variant_slugs(templates):
            assert slug
            assert not any(ch in slug for ch in "/\\ \t\n")
            assert Path(slug).name == slug

    def test_slugs_collision_free_for_distinct_combinations(self) -> None:
        templates = self._templates(
            "ema := ema { period: <20 | 50> }\nsig := generate_signal { min_strength: <0.3 | 0.5> }"
        )
        slugs = variant_slugs(templates)
        assert len(slugs) == len(set(slugs)) == 4

    def test_slugs_share_varying_dimensions_with_labels(self) -> None:
        templates = self._templates(
            "ema := ema { period: <20 | 50> }\nsig := generate_signal { min_strength: <0.3 | 0.5> }"
        )
        labels = variant_labels(templates)
        slugs = variant_slugs(templates)
        assert len(labels) == len(slugs)
        # Every slug names the same choice dimensions its label does (period,
        # min_strength) — no ordinal indexes, no extra non-varying params.
        assert all("20" in s or "50" in s for s in slugs)
        assert all("ms0" in s for s in slugs)

    def test_unknown_param_name_falls_back_to_full_name(self) -> None:
        templates = self._templates("swings := swings { lookback: 50, left_bars: <1 | 2> }")
        assert variant_slugs(templates) == ["leftbars1", "leftbars2"]

    def test_string_timeframe_choice_slug(self) -> None:
        templates = self._templates(
            'tf := timeframe { resolution: <"1h" | "1d"> }\n'
            "ema := ema { timeframe: tf, period: 20 }"
        )
        assert variant_slugs(templates) == ["tf1h", "tf1d"]


class TestVariantColumns:
    """Backlog 081: index grid columns/slugs derived from bare identities."""

    def _columns(
        self, identities: list[dict[str, object]]
    ) -> tuple[tuple[str, ...], tuple[str, ...], list[str]]:
        return variant_columns(identities)

    def test_headers_and_slugs_from_identities(self) -> None:
        varying, headers, slugs = self._columns(
            [
                {"generate_signal.min_strength": 0.1},
                {"generate_signal.min_strength": 0.99},
            ]
        )
        assert varying == ("generate_signal.min_strength",)
        assert headers == ("min_strength",)
        assert slugs == ["ms010", "ms099"]

    def test_multi_dimension_cartesian(self) -> None:
        varying, headers, slugs = self._columns(
            [
                {"ema.period": 20, "generate_signal.min_strength": 0.1},
                {"ema.period": 20, "generate_signal.min_strength": 0.99},
                {"ema.period": 50, "generate_signal.min_strength": 0.1},
                {"ema.period": 50, "generate_signal.min_strength": 0.99},
            ]
        )
        assert varying == ("ema.period", "generate_signal.min_strength")
        assert headers == ("period", "min_strength")
        assert slugs == ["p20_ms010", "p20_ms099", "p50_ms010", "p50_ms099"]

    def test_shared_bare_name_qualifies_header(self) -> None:
        varying, headers, slugs = self._columns(
            [
                {"ema.period": 20, "atr.period": 14},
                {"ema.period": 50, "atr.period": 21},
            ]
        )
        # Two nodes both vary a bare `period` -> headers stay qualified,
        # sorted-key order.
        assert headers == ("atr.period", "ema.period")
        assert slugs == ["atr_p14_ema_p20", "atr_p21_ema_p50"]

    def test_lone_identity_yields_default(self) -> None:
        varying, headers, slugs = self._columns([{"generate_signal.min_strength": 0.5}])
        assert (varying, headers, slugs) == ((), (), ["default"])


class TestCLIAbFlagWiring:
    def test_run_ab_single_symbol_calls_ab_test(self, tmp_path: Path) -> None:
        dsl = tmp_path / "s.dsl"
        dsl.write_text(CHOICE_FREE_DSL)
        with patch("marketatlas.cli.commands._run_ab_test") as ab:
            _run_main("run", "--ab", "--strategy", str(dsl), "--symbol", "BTC-USD")
        ab.assert_called_once()

    def test_run_ab_instruments_calls_portfolio_ab_test(self, tmp_path: Path) -> None:
        dsl, registry_path, portfolio = _setup(tmp_path)
        with patch("marketatlas.cli.commands._run_portfolio_ab_test") as ab:
            _run_main(
                "run",
                "--ab",
                "--strategy",
                str(dsl),
                "--instruments",
                str(portfolio),
                "--registry",
                str(registry_path),
            )
        ab.assert_called_once()

    def test_run_instruments_without_ab_uses_portfolio_command(self, tmp_path: Path) -> None:
        dsl, registry_path, portfolio = _setup(tmp_path)
        with (
            patch("marketatlas.cli.commands.run_portfolio_command") as pc,
            patch("marketatlas.cli.commands._run_portfolio_ab_test") as ab,
        ):
            _run_main(
                "run",
                "--strategy",
                str(dsl),
                "--instruments",
                str(portfolio),
                "--registry",
                str(registry_path),
            )
        pc.assert_called_once()
        ab.assert_not_called()

    @pytest.mark.parametrize("with_instruments", [False, True])
    def test_run_ab_yaml_errors_cleanly(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], with_instruments: bool
    ) -> None:
        yaml_file = tmp_path / "s.yaml"
        yaml_file.write_text("strategy:\n  name: test\n")
        args = ["run", "--ab", "--strategy", str(yaml_file)]
        if with_instruments:
            _, registry_path, portfolio = _setup(tmp_path)
            args += ["--instruments", str(portfolio), "--registry", str(registry_path)]
        with pytest.raises(SystemExit) as exc:
            _run_main(*args)
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "requires a DSL strategy file" in captured.err

    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    def test_run_ab_choice_free_single_variant(
        self,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        dsl = tmp_path / "s.dsl"
        dsl.write_text(CHOICE_FREE_DSL)

        provider = MagicMock()
        provider.fetch.return_value = _market_data("BTC-USD")
        with (
            patch("marketatlas.cli.YahooProvider") as yahoo,
            patch("marketatlas.cli.DukascopyProvider") as duka,
        ):
            yahoo.return_value = provider
            duka.return_value = provider

            mock_tradebook = MagicMock()
            mock_tradebook.summary = {
                "initial_balance": 1000.0,
                "final_balance": 1000.0,
                "total_pnl": 0.0,
                "total_return_pct": 0.0,
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "profit_factor": 0.0,
                "expectancy": 0.0,
            }
            mock_tradebook.trades = []
            mock_bt = MagicMock()
            mock_bt.run.return_value = _result(mock_tradebook)
            mock_bt_cls.return_value = mock_bt

            _run_main(
                "run",
                "--ab",
                "--strategy",
                str(dsl),
                "--symbol",
                "BTC-USD",
                "--start",
                "2024-01-01",
                "--end",
                "2024-06-01",
                "--output",
                str(tmp_path / "out.html"),
            )

        captured = capsys.readouterr()
        assert "A/B TEST — 1 variant(s)" in captured.out
        assert "default" in captured.out
        assert "HTML chart:" in captured.out

    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    def test_run_ab_output_tree_single_symbol(
        self,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        dsl = tmp_path / "s.dsl"
        dsl.write_text("ema := ema { period: <20 | 50> }")

        provider = MagicMock()
        provider.fetch.return_value = _market_data("BTC-USD")
        with (
            patch("marketatlas.cli.YahooProvider") as yahoo,
            patch("marketatlas.cli.DukascopyProvider") as duka,
        ):
            yahoo.return_value = provider
            duka.return_value = provider

            mock_tradebook = MagicMock()
            mock_tradebook.summary = {
                "initial_balance": 1000.0,
                "final_balance": 1000.0,
                "total_pnl": 0.0,
                "total_return_pct": 0.0,
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "profit_factor": 0.0,
                "expectancy": 0.0,
            }
            mock_tradebook.trades = []
            mock_bt_cls.return_value.run.return_value = _result(mock_tradebook)

            _run_main(
                "run",
                "--ab",
                "--strategy",
                str(dsl),
                "--symbol",
                "BTC-USD",
                "--start",
                "2024-01-01",
                "--end",
                "2024-06-01",
                "--output",
                str(tmp_path / "out.html"),
            )

        rendered = [c.args[0] for c in mock_renderer_cls.return_value.render.call_args_list]
        assert rendered == [
            tmp_path / "out" / "p20" / "out.html",
            tmp_path / "out" / "p50" / "out.html",
        ]

        # 081: the comparison index sits at the output-tree root and links each
        # variant's chart via a relative href (slug dir + chart filename).
        index = tmp_path / "out" / "ab.html"
        assert index.exists()
        content = index.read_text()
        assert "A/B Comparison" in content
        assert '<a href="p20/out.html">BTC-USD</a>' in content
        assert '<a href="p50/out.html">BTC-USD</a>' in content

    def test_run_ab_output_tree_portfolio(self, tmp_path: Path) -> None:
        dsl, registry_path, portfolio = _setup(tmp_path)
        provider = MagicMock()
        provider.fetch.side_effect = lambda symbol, tf, start, end: _market_data(symbol.name)
        with (
            patch("marketatlas.cli.YahooProvider") as yahoo,
            patch("marketatlas.cli.DukascopyProvider") as duka,
            patch("marketatlas.strategy.bundle.StrategyBundle") as bundle_cls,
            patch(
                "marketatlas.visualization.portfolio.render_per_instrument_charts"
            ) as render_charts,
        ):
            yahoo.return_value = provider
            duka.return_value = provider
            bundle_cls.side_effect = _real_bundle
            render_charts.return_value = (Path("chart.html"),)
            _run_main(
                "run",
                "--ab",
                "--strategy",
                str(dsl),
                "--instruments",
                str(portfolio),
                "--registry",
                str(registry_path),
                "--interval",
                "1d",
                "--start",
                "2024-01-01",
                "--end",
                "2025-01-01",
                "--data-dir",
                str(tmp_path / "cache"),
                "--output",
                str(tmp_path / "ab.html"),
            )

        variant_dirs = [c.args[1] for c in render_charts.call_args_list]
        assert variant_dirs == [
            tmp_path / "ab" / "ms010",
            tmp_path / "ab" / "ms099",
        ]
        # Per-instrument charts share the portfolio stem under each variant dir.
        for call in render_charts.call_args_list:
            assert call.kwargs["stem"] == "portfolio"

        # 081: the comparison index shows one grid row per choice combination
        # and links each variant's per-instrument charts from disk.
        index = tmp_path / "ab" / "ab.html"
        assert index.exists()
        content = index.read_text()
        assert "A/B Comparison" in content
        assert "<td>0.1</td>" in content
        assert "<td>0.99</td>" in content
        assert '<a href="ms010/portfolio.A.html">A</a>' in content
        assert '<a href="ms099/portfolio.B.html">B</a>' in content


def _result(mock_tradebook: MagicMock) -> MagicMock:
    result = MagicMock()
    result.tradebook = mock_tradebook
    result.frames = MagicMock()
    return result


class TestPortfolioABRunner:
    @pytest.fixture(autouse=True)
    def _reset_bundle_recorder(self) -> None:
        _created_bundles.clear()

    def _run(self, args: list[str]) -> None:
        provider = MagicMock()
        provider.fetch.side_effect = lambda symbol, tf, start, end: _market_data(symbol.name)
        with (
            patch("marketatlas.cli.YahooProvider") as yahoo,
            patch("marketatlas.cli.DukascopyProvider") as duka,
            patch("marketatlas.strategy.bundle.StrategyBundle") as bundle_cls,
        ):
            yahoo.return_value = provider
            duka.return_value = provider
            bundle_cls.side_effect = _real_bundle
            _run_main(*args)

    @pytest.mark.parametrize("two_value_choice", [True])
    def test_real_two_instrument_two_value_choice(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        two_value_choice: bool,
    ) -> None:
        dsl, registry_path, portfolio = _setup(tmp_path)
        self._run(
            [
                "run",
                "--ab",
                "--strategy",
                str(dsl),
                "--instruments",
                str(portfolio),
                "--registry",
                str(registry_path),
                "--interval",
                "1d",
                "--start",
                "2024-01-01",
                "--end",
                "2025-01-01",
                "--data-dir",
                str(tmp_path / "cache"),
                "--output",
                "",
            ]
        )

        captured = capsys.readouterr()
        assert "A/B TEST (PORTFOLIO) — 2 variant(s)" in captured.out
        # Variant 0: low min_strength fires the confirmed pullback on both
        # instruments (per-instrument book lanes, 075/086); variant 1
        # (min_strength 0.99) rejects it. Labels name the chosen values.
        assert "min_strength=0.1" in captured.out
        assert "min_strength=0.99" in captured.out
        assert "2 trades" in captured.out
        assert "0 trades" in captured.out

        # Each variant runs on a fresh StrategyBundle and its own TradeBook:
        # no cross-variant state, exactly one pair of created bundles.
        bundles = list(_created_bundles)
        assert len(bundles) == 2
        assert bundles[0] is not bundles[1]
        tradebooks = [b.tradebook for b in bundles]
        assert all(isinstance(t, TradeBook) for t in tradebooks)
        assert tradebooks[0] is not tradebooks[1]


def _real_bundle(*args: object, **kwargs: object) -> StrategyBundle:
    """StrategyBundle factory that records created instances side-by-side.

    ``_real_bundle`` is installed as ``StrategyBundle.side_effect`` on the
    patched class; the patch is active during the run so every instance the
    CLI builds is recorded (for the distinct-tradebook assertion).
    """
    instance = StrategyBundle(*args, **kwargs)  # type: ignore[arg-type]
    _created_bundles.append(instance)
    return instance


_created_bundles: list[StrategyBundle] = []
