from __future__ import annotations

from pathlib import Path

import pytest
from marketatlas.config import app_config_dir, instruments_registry_path, xdg_config_home


def test_xdg_config_home_honours_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert xdg_config_home() == tmp_path / "xdg"


def test_xdg_config_home_defaults_to_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert xdg_config_home() == Path.home() / ".config"


def test_app_config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert app_config_dir() == tmp_path / "xdg" / "marketatlas"


def test_instruments_registry_prefers_user_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg = tmp_path / "xdg"
    (xdg / "marketatlas").mkdir(parents=True)
    user = xdg / "marketatlas" / "instruments.yaml"
    user.write_text("instruments: {}\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "instruments.yaml").write_text("instruments: {}\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.chdir(tmp_path)
    assert instruments_registry_path() == user


def test_instruments_registry_falls_back_to_legacy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg = tmp_path / "xdg"
    (xdg / "marketatlas").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "instruments.yaml").write_text("instruments: {}\n")
    monkeypatch.chdir(tmp_path)
    assert instruments_registry_path() == Path("data/instruments.yaml")


def test_instruments_registry_absent_returns_legacy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    assert instruments_registry_path() == Path("data/instruments.yaml")
