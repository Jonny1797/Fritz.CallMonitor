"""App-Konfiguration (ohne Passwort - siehe credentials.py) als TOML-Datei.

phonebook_ids ist absichtlich eine TOML-kompatible Liste statt None: eine leere
Liste bedeutet "alle Telefonbücher der Box einbeziehen".
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

import tomli_w

from fritz_callhistory.paths import config_file


@dataclass
class Config:
    address: str = "192.168.178.1"
    username: str = ""
    sync_interval_minutes: int = 30
    phonebook_ids: list[int] = field(default_factory=list)
    show_incoming_call_popup: bool = True
    minimize_to_tray_on_close: bool = False

    def resolved_phonebook_ids(self) -> list[int] | None:
        """None bedeutet für den SyncService "alle Telefonbücher der Box"."""
        return self.phonebook_ids or None


def load(path: Path | None = None) -> Config:
    path = path or config_file()
    if not path.exists():
        return Config()
    with path.open("rb") as file:
        data = tomllib.load(file)
    known_fields = {field_.name for field_ in Config.__dataclass_fields__.values()}
    return Config(**{key: value for key, value in data.items() if key in known_fields})


def save(config: Config, path: Path | None = None) -> None:
    path = path or config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump(asdict(config), f)
