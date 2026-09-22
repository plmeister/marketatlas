"""User-level configuration resolution.

Config files live under the XDG config dir (``~/.config/marketatlas`` by
default) rather than inside the repository, so fresh checkouts and tend
worktrees see the same configuration as the main workspace.  Repo-local
``data/`` paths are kept as a legacy fallback only.
"""
from __future__ import annotations

import os
from pathlib import Path

_APP_DIR_NAME = "marketatlas"
REGISTRY_FILENAME = "instruments.yaml"
_LEGACY_REGISTRY_PATH = Path("data/instruments.yaml")


def xdg_config_home() -> Path:
    env = os.environ.get("XDG_CONFIG_HOME")
    return Path(env) if env else Path.home() / ".config"


def app_config_dir() -> Path:
    """Per-app config dir (``XDG_CONFIG_HOME/marketatlas``)."""
    return xdg_config_home() / _APP_DIR_NAME


def instruments_registry_path() -> Path:
    """Resolve the instruments registry path.

    User config takes precedence; a repo-local ``data/instruments.yaml`` is
    honoured as a legacy fallback when no user config exists.
    """
    user = app_config_dir() / REGISTRY_FILENAME
    if user.is_file():
        return user
    return _LEGACY_REGISTRY_PATH
