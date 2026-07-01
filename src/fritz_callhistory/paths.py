"""Zentrale, plattformunabhängige Pfade (Config/Daten/Logs) via platformdirs."""

from __future__ import annotations

from pathlib import Path

import platformdirs

APP_NAME = "FritzCallHistory"
APP_AUTHOR = "fritz-callhistory"


def config_file() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME, APP_AUTHOR)) / "config.toml"


def database_file() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR)) / "callhistory.sqlite3"


def log_dir() -> Path:
    return Path(platformdirs.user_log_dir(APP_NAME, APP_AUTHOR))
