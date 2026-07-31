from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETATLAS_DATA_DIR", str(tmp_path / "marketatlas-cache"))


def _make_candles(n: int = 5, base_price: float = 100.0) -> tuple[Candle, ...]:
    from datetime import timedelta

    base = datetime(2024, 1, 1, tzinfo=UTC)
    candles = []
    for i in range(n):
        ts = base + timedelta(days=i)
        p = base_price + i
        candles.append(
            Candle(timestamp=ts, open=p, high=p + 2, low=p - 1, close=p + 1, volume=1000.0 + i)
        )
    return tuple(candles)


def _make_market_data(
    symbol: str = "TEST", timeframe: Timeframe = Timeframe.D1, n: int = 200
) -> MarketData:
    return MarketData(
        symbol=Symbol(symbol),
        timeframe=timeframe,
        candles=_make_candles(n, 100.0),
    )


def _run_main(*args: str) -> None:
    with patch("sys.argv", ["marketatlas", *args]):
        from marketatlas.cli import main

        main()


class TestMainEntry:
    def test_no_command_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        _run_main()
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or "marketatlas" in captured.out.lower()


class TestFetchCommand:
    @patch("marketatlas.cli.YahooProvider")
    def test_fetch_success(self, mock_yahoo_cls: MagicMock, tmp_path: Path) -> None:
        candles = _make_candles(3)
        market_data = MarketData(symbol=Symbol("BTC-USD"), timeframe=Timeframe.D1, candles=candles)
        mock_provider = MagicMock()
        mock_provider.fetch.return_value = market_data
        mock_yahoo_cls.return_value = mock_provider

        _run_main(
            "fetch",
            "--symbol",
            "BTC-USD",
            "--timeframe",
            "1d",
            "--start",
            "2024-01-01",
            "--end",
            "2024-02-01",
            "--output",
            str(tmp_path),
        )

        mock_provider.fetch.assert_called_once()
        saved = tmp_path / "BTC-USD.1d.parquet"
        assert saved.exists()

    @patch("marketatlas.cli.YahooProvider")
    def test_fetch_creates_output_dir(self, mock_yahoo_cls: MagicMock, tmp_path: Path) -> None:
        mock_provider = MagicMock()
        mock_provider.fetch.return_value = MarketData(
            symbol=Symbol("X"), timeframe=Timeframe.D1, candles=()
        )
        mock_yahoo_cls.return_value = mock_provider

        out_dir = tmp_path / "nested" / "dir"
        _run_main(
            "fetch",
            "--symbol",
            "X",
            "--timeframe",
            "1d",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-02",
            "--output",
            str(out_dir),
        )

        assert out_dir.exists()

    @patch("marketatlas.cli.YahooProvider")
    def test_fetch_provider_error(self, mock_yahoo_cls: MagicMock, tmp_path: Path) -> None:
        mock_provider = MagicMock()
        mock_provider.fetch.side_effect = RuntimeError("network down")
        mock_yahoo_cls.return_value = mock_provider

        with pytest.raises(SystemExit) as exc_info:
            _run_main(
                "fetch",
                "--symbol",
                "BAD",
                "--timeframe",
                "1d",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-02",
                "--output",
                str(tmp_path),
            )
        assert exc_info.value.code == 1


class TestRunCommand:
    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    @patch("marketatlas.strategy.bundle.StrategyBundle")
    @patch("marketatlas.strategy.strategy.Strategy")
    @patch("marketatlas.strategy.loader.load_strategy")
    @patch("marketatlas.cli.YahooProvider")
    def test_run_success(
        self,
        mock_yahoo_cls: MagicMock,
        mock_load: MagicMock,
        mock_strategy_cls: MagicMock,
        mock_bundle_cls: MagicMock,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        strategy_file = tmp_path / "strat.yaml"
        strategy_file.write_text("strategy:\n  name: test\n")

        config = MagicMock()
        config.name = "test"
        config.version = "1.0"
        config.analyzers = [1, 2]
        config.signals = [1]
        mock_load.return_value = config

        mock_provider = MagicMock()
        mock_provider.fetch.return_value = _make_market_data(n=200)
        mock_yahoo_cls.return_value = mock_provider

        mock_strategy_cls.return_value = MagicMock()
        mock_bundle_cls.return_value = MagicMock()

        mock_bt = MagicMock()
        mock_bt.frame_count = 100
        mock_bt._max_hold_days = 10
        mock_tradebook = MagicMock()
        mock_tradebook.summary = {
            "initial_balance": 1000.0,
            "final_balance": 1100.0,
            "total_pnl": 100.0,
            "total_return_pct": 10.0,
            "total_trades": 8,
            "wins": 5,
            "losses": 3,
            "breakevens": 0,
            "win_rate": 0.625,
            "max_drawdown": 0.05,
            "profit_factor": 2.0,
            "expectancy": 12.5,
            "by_strategy": {"test": {"wins": 5, "losses": 3, "total_pnl": 100.0}},
        }
        mock_tradebook.trades = []
        mock_bt.run_with_progress.return_value = (MagicMock(), mock_tradebook)
        mock_bt_cls.return_value = mock_bt

        output_html = tmp_path / "out.html"
        _run_main(
            "run",
            "--strategy",
            str(strategy_file),
            "--symbol",
            "BTC-USD",
            "--interval",
            "1d",
            "--start",
            "2024-01-01",
            "--end",
            "2025-01-01",
            "--output",
            str(output_html),
            "--balance",
            "5000",
            "--max-hold-days",
            "5",
        )

        mock_load.assert_called_once_with(strategy_file)
        mock_bt.run_with_progress.assert_called_once()
        mock_renderer_cls.assert_called_once()
        mock_renderer_cls.return_value.render.assert_called_once_with(output_html)

    def test_run_strategy_not_found(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nope.yaml"
        with pytest.raises(SystemExit) as exc_info:
            _run_main("run", "--strategy", str(nonexistent))
        assert exc_info.value.code == 1

    @patch("marketatlas.strategy.loader.load_strategy")
    def test_run_strategy_load_error(self, mock_load: MagicMock, tmp_path: Path) -> None:
        strategy_file = tmp_path / "bad.yaml"
        strategy_file.write_text("invalid")
        mock_load.side_effect = ValueError("bad config")

        with pytest.raises(SystemExit) as exc_info:
            _run_main("run", "--strategy", str(strategy_file))
        assert exc_info.value.code == 1

    @patch("marketatlas.cli.YahooProvider")
    @patch("marketatlas.strategy.loader.load_strategy")
    def test_run_provider_error(
        self,
        mock_load: MagicMock,
        mock_yahoo_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        strategy_file = tmp_path / "strat.yaml"
        strategy_file.write_text("strategy:\n  name: test\n")

        config = MagicMock()
        config.name = "test"
        config.version = "1.0"
        config.analyzers = []
        config.signals = []
        mock_load.return_value = config

        mock_provider = MagicMock()
        mock_provider.fetch.side_effect = RuntimeError("network error")
        mock_yahoo_cls.return_value = mock_provider

        with pytest.raises(SystemExit) as exc_info:
            _run_main("run", "--strategy", str(strategy_file))
        assert exc_info.value.code == 1

    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    @patch("marketatlas.strategy.bundle.StrategyBundle")
    @patch("marketatlas.strategy.strategy.Strategy")
    @patch("marketatlas.strategy.loader.load_strategy")
    @patch("marketatlas.cli.YahooProvider")
    def test_run_with_output_renders_html(
        self,
        mock_yahoo_cls: MagicMock,
        mock_load: MagicMock,
        mock_strategy_cls: MagicMock,
        mock_bundle_cls: MagicMock,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        strategy_file = tmp_path / "strat.yaml"
        strategy_file.write_text("strategy:\n  name: test\n")

        config = MagicMock()
        config.name = "test"
        config.version = "1.0"
        config.analyzers = []
        config.signals = []
        mock_load.return_value = config

        mock_provider = MagicMock()
        mock_provider.fetch.return_value = _make_market_data(n=200)
        mock_yahoo_cls.return_value = mock_provider

        mock_strategy_cls.return_value = MagicMock()
        mock_bundle_cls.return_value = MagicMock()

        mock_bt = MagicMock()
        mock_bt.frame_count = 100
        mock_bt._max_hold_days = 10
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
            "by_strategy": {},
        }
        mock_tradebook.trades = []
        mock_bt.run_with_progress.return_value = (MagicMock(), mock_tradebook)
        mock_bt_cls.return_value = mock_bt

        output_html = tmp_path / "output.html"
        _run_main(
            "run",
            "--strategy",
            str(strategy_file),
            "--output",
            str(output_html),
        )

        mock_renderer_cls.assert_called_once()
        mock_renderer_cls.return_value.render.assert_called_once_with(output_html)

    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    @patch("marketatlas.strategy.bundle.StrategyBundle")
    @patch("marketatlas.strategy.strategy.Strategy")
    @patch("marketatlas.strategy.loader.load_strategy")
    @patch("marketatlas.cli.YahooProvider")
    def test_run_displays_trade_log(
        self,
        mock_yahoo_cls: MagicMock,
        mock_load: MagicMock,
        mock_strategy_cls: MagicMock,
        mock_bundle_cls: MagicMock,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        strategy_file = tmp_path / "strat.yaml"
        strategy_file.write_text("strategy:\n  name: test\n")

        config = MagicMock()
        config.name = "test"
        config.version = "1.0"
        config.analyzers = []
        config.signals = []
        mock_load.return_value = config

        mock_provider = MagicMock()
        mock_provider.fetch.return_value = _make_market_data(n=200)
        mock_yahoo_cls.return_value = mock_provider

        mock_strategy_cls.return_value = MagicMock()
        mock_bundle_cls.return_value = MagicMock()

        mock_bt = MagicMock()
        mock_bt.frame_count = 100
        mock_bt._max_hold_days = 10

        mock_candidate = MagicMock()
        mock_candidate.direction.value = "bullish"
        mock_candidate.entry = 105.0
        mock_candidate.stop = 100.0
        mock_candidate.target = 115.0
        mock_candidate.rr_ratio = 2.0
        mock_candidate.size = 10

        mock_trade = MagicMock()
        mock_trade.entry_timestamp = datetime(2024, 1, 5, tzinfo=UTC)
        mock_trade.exit_timestamp = datetime(2024, 1, 10, tzinfo=UTC)
        mock_trade.candidate = mock_candidate
        mock_trade.pnl = 50.0
        mock_trade.result = "win"
        mock_trade.source_strategy = "test"

        mock_tradebook = MagicMock()
        mock_tradebook.summary = {
            "initial_balance": 1000.0,
            "final_balance": 1050.0,
            "total_pnl": 50.0,
            "total_return_pct": 5.0,
            "total_trades": 1,
            "wins": 1,
            "losses": 0,
            "breakevens": 0,
            "win_rate": 1.0,
            "max_drawdown": 0.0,
            "profit_factor": 999.0,
            "expectancy": 50.0,
            "by_strategy": {},
        }
        mock_tradebook.trades = [mock_trade]
        mock_bt.run_with_progress.return_value = (MagicMock(), mock_tradebook)
        mock_bt_cls.return_value = mock_bt

        _run_main(
            "run",
            "--strategy",
            str(strategy_file),
            "--output",
            "",
        )

    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    @patch("marketatlas.strategy.bundle.StrategyBundle")
    @patch("marketatlas.strategy.strategy.Strategy")
    @patch("marketatlas.strategy.loader.load_strategy")
    @patch("marketatlas.cli.YahooProvider")
    def test_run_no_dates_uses_defaults(
        self,
        mock_yahoo_cls: MagicMock,
        mock_load: MagicMock,
        mock_strategy_cls: MagicMock,
        mock_bundle_cls: MagicMock,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        strategy_file = tmp_path / "strat.yaml"
        strategy_file.write_text("strategy:\n  name: test\n")

        config = MagicMock()
        config.name = "test"
        config.version = "1.0"
        config.analyzers = []
        config.signals = []
        mock_load.return_value = config

        mock_provider = MagicMock()
        mock_provider.fetch.return_value = _make_market_data(n=200)
        mock_yahoo_cls.return_value = mock_provider

        mock_strategy_cls.return_value = MagicMock()
        mock_bundle_cls.return_value = MagicMock()

        mock_bt = MagicMock()
        mock_bt.frame_count = 100
        mock_bt._max_hold_days = 10
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
            "by_strategy": {},
        }
        mock_tradebook.trades = []
        mock_bt.run_with_progress.return_value = (MagicMock(), mock_tradebook)
        mock_bt_cls.return_value = mock_bt

        _run_main(
            "run",
            "--strategy",
            str(strategy_file),
            "--output",
            "",
        )

        fetch_args = mock_provider.fetch.call_args
        start_dt = fetch_args[0][2]
        end_dt = fetch_args[0][3]
        assert start_dt < datetime.now()
        assert end_dt.date() == datetime.now().date()

    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    @patch("marketatlas.strategy.bundle.StrategyBundle")
    @patch("marketatlas.strategy.strategy.Strategy")
    @patch("marketatlas.strategy.loader.load_strategy")
    @patch("marketatlas.cli.YahooProvider")
    def test_run_multi_timeframe(
        self,
        mock_yahoo_cls: MagicMock,
        mock_load: MagicMock,
        mock_strategy_cls: MagicMock,
        mock_bundle_cls: MagicMock,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        strategy_file = tmp_path / "multi_tf.yaml"
        strategy_file.write_text("strategy:\n  name: multi_tf\n  timeframes:\n    - 1d\n    - 1w\n")

        config = MagicMock()
        config.name = "multi_tf"
        config.version = "1.0"
        config.analyzers = []
        config.signals = []
        config.timeframes = ("1d", "1w")
        mock_load.return_value = config

        mock_provider = MagicMock()
        mock_provider.fetch.side_effect = [
            _make_market_data(n=200),  # D1 fetch succeeds
            _make_market_data(n=200),  # W1 fetch also succeeds
        ]
        mock_yahoo_cls.return_value = mock_provider

        mock_strategy_cls.return_value = MagicMock()
        mock_bundle_cls.return_value = MagicMock()

        mock_bt = MagicMock()
        mock_bt.frame_count = 100
        mock_bt._max_hold_days = 10
        mock_tradebook = MagicMock()
        mock_tradebook.summary = {
            "initial_balance": 1000.0, "final_balance": 1000.0,
            "total_pnl": 0.0, "total_return_pct": 0.0,
            "total_trades": 0, "wins": 0, "losses": 0, "breakevens": 0,
            "win_rate": 0.0, "max_drawdown": 0.0, "profit_factor": 0.0,
            "expectancy": 0.0, "by_strategy": {},
        }
        mock_tradebook.trades = []
        mock_bt.run_with_progress.return_value = (MagicMock(), mock_tradebook)
        mock_bt_cls.return_value = mock_bt

        output_html = tmp_path / "multi.html"
        _run_main(
            "run",
            "--strategy", str(strategy_file),
            "--interval", "1d",
            "--output", str(output_html),
        )

        assert mock_provider.fetch.call_count == 2

    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    @patch("marketatlas.strategy.bundle.StrategyBundle")
    @patch("marketatlas.strategy.strategy.Strategy")
    @patch("marketatlas.strategy.loader.load_strategy")
    @patch("marketatlas.cli.YahooProvider")
    def test_run_multi_timeframe_resample_fallback(
        self,
        mock_yahoo_cls: MagicMock,
        mock_load: MagicMock,
        mock_strategy_cls: MagicMock,
        mock_bundle_cls: MagicMock,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        strategy_file = tmp_path / "resample.yaml"
        strategy_file.write_text(
            "strategy:\n  name: resample_test\n  timeframes:\n    - 1d\n    - 1w\n"
        )

        config = MagicMock()
        config.name = "resample_test"
        config.version = "1.0"
        config.analyzers = []
        config.signals = []
        config.timeframes = ("1d", "1w")
        mock_load.return_value = config

        mock_provider = MagicMock()
        # D1 succeeds, W1 raises ValueError (unsupported)
        mock_provider.fetch.side_effect = [
            _make_market_data(n=200),
            ValueError("Unsupported timeframe: Timeframe.W1"),
        ]
        mock_yahoo_cls.return_value = mock_provider

        mock_strategy_cls.return_value = MagicMock()
        mock_bundle_cls.return_value = MagicMock()

        mock_bt = MagicMock()
        mock_bt.frame_count = 100
        mock_bt._max_hold_days = 10
        mock_tradebook = MagicMock()
        mock_tradebook.summary = {
            "initial_balance": 1000.0, "final_balance": 1000.0,
            "total_pnl": 0.0, "total_return_pct": 0.0,
            "total_trades": 0, "wins": 0, "losses": 0, "breakevens": 0,
            "win_rate": 0.0, "max_drawdown": 0.0, "profit_factor": 0.0,
            "expectancy": 0.0, "by_strategy": {},
        }
        mock_tradebook.trades = []
        mock_bt.run_with_progress.return_value = (MagicMock(), mock_tradebook)
        mock_bt_cls.return_value = mock_bt

        output_html = tmp_path / "resample.html"
        _run_main(
            "run",
            "--strategy", str(strategy_file),
            "--interval", "1d",
            "--output", str(output_html),
        )

        assert mock_provider.fetch.call_count == 2

    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    @patch("marketatlas.strategy.bundle.StrategyBundle")
    @patch("marketatlas.strategy.strategy.Strategy")
    @patch("marketatlas.strategy.loader.load_strategy")
    @patch("marketatlas.cli.YahooProvider")
    def test_run_second_run_served_from_store(
        self,
        mock_yahoo_cls: MagicMock,
        mock_load: MagicMock,
        mock_strategy_cls: MagicMock,
        mock_bundle_cls: MagicMock,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        strategy_file = tmp_path / "strat.yaml"
        strategy_file.write_text("strategy:\n  name: test\n")

        config = MagicMock()
        config.name = "test"
        config.version = "1.0"
        config.analyzers = []
        config.signals = []
        config.timeframes = ()
        mock_load.return_value = config

        mock_provider = MagicMock()
        mock_provider.fetch.return_value = _make_market_data(symbol="BTC-USD", n=200)
        mock_yahoo_cls.return_value = mock_provider

        mock_strategy_cls.return_value = MagicMock()
        mock_bundle_cls.return_value = MagicMock()

        mock_bt = MagicMock()
        mock_bt.frame_count = 100
        mock_bt._max_hold_days = 10
        mock_tradebook = MagicMock()
        mock_tradebook.summary = {
            "initial_balance": 1000.0, "final_balance": 1000.0,
            "total_pnl": 0.0, "total_return_pct": 0.0,
            "total_trades": 0, "wins": 0, "losses": 0, "breakevens": 0,
            "win_rate": 0.0, "max_drawdown": 0.0, "profit_factor": 0.0,
            "expectancy": 0.0, "by_strategy": {},
        }
        mock_tradebook.trades = []
        mock_bt.run_with_progress.return_value = (MagicMock(), mock_tradebook)
        mock_bt_cls.return_value = mock_bt

        data_dir = tmp_path / "cache"
        args = [
            "run", "--strategy", str(strategy_file),
            "--interval", "1d",
            "--data-dir", str(data_dir),
            "--output", "",
            "--start", "2024-01-01", "--end", "2024-06-01",
        ]
        _run_main(*args)
        assert mock_provider.fetch.call_count >= 1

        mock_provider.fetch.reset_mock()
        _run_main(*args)
        assert mock_provider.fetch.call_count == 0

    @patch("marketatlas.visualization.interactive.InteractiveRenderer")
    @patch("marketatlas.backtesting.backtester.Backtester")
    @patch("marketatlas.strategy.bundle.StrategyBundle")
    @patch("marketatlas.strategy.strategy.Strategy")
    @patch("marketatlas.strategy.loader.load_strategy")
    @patch("marketatlas.cli.YahooProvider")
    def test_run_shows_by_strategy_breakdown(
        self,
        mock_yahoo_cls: MagicMock,
        mock_load: MagicMock,
        mock_strategy_cls: MagicMock,
        mock_bundle_cls: MagicMock,
        mock_bt_cls: MagicMock,
        mock_renderer_cls: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        strategy_file = tmp_path / "strat.yaml"
        strategy_file.write_text("strategy:\n  name: test\n")

        config = MagicMock()
        config.name = "test"
        config.version = "1.0"
        config.analyzers = []
        config.signals = []
        mock_load.return_value = config

        mock_provider = MagicMock()
        mock_provider.fetch.return_value = _make_market_data(n=200)
        mock_yahoo_cls.return_value = mock_provider

        mock_strategy_cls.return_value = MagicMock()
        mock_bundle_cls.return_value = MagicMock()

        mock_bt = MagicMock()
        mock_bt.frame_count = 100
        mock_bt._max_hold_days = 10
        mock_tradebook = MagicMock()
        mock_tradebook.summary = {
            "initial_balance": 1000.0,
            "final_balance": 1100.0,
            "total_pnl": 100.0,
            "total_return_pct": 10.0,
            "total_trades": 3,
            "wins": 2,
            "losses": 1,
            "breakevens": 0,
            "win_rate": 0.667,
            "max_drawdown": 0.03,
            "profit_factor": 3.0,
            "expectancy": 33.3,
            "by_strategy": {
                "alpha": {"wins": 2, "losses": 0, "total_pnl": 80.0},
                "beta": {"wins": 0, "losses": 1, "total_pnl": -20.0},
            },
        }
        mock_tradebook.trades = []
        mock_bt.run_with_progress.return_value = (MagicMock(), mock_tradebook)
        mock_bt_cls.return_value = mock_bt

        _run_main(
            "run",
            "--strategy",
            str(strategy_file),
            "--output",
            "",
        )

        captured = capsys.readouterr()
        assert "alpha" in captured.out
        assert "beta" in captured.out


class TestParserValidation:
    def test_fetch_missing_required_args(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            _run_main("fetch")
        assert exc_info.value.code != 0

    def test_run_missing_strategy(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            _run_main("run")
        assert exc_info.value.code != 0
