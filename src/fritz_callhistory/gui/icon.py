"""Lädt das App-Icon als QIcon.

Gleiches importlib.resources-Muster wie db/schema.py's _migrations(): funktioniert
identisch im Dev-Betrieb und im PyInstaller-Onefile-Build (dort kommt die Datei aus
dem via packaging/fritz_callhistory.spec gebündelten Datenverzeichnis).
"""

from __future__ import annotations

from importlib import resources

from PySide6.QtGui import QIcon


def app_icon() -> QIcon:
    icon_path = resources.files("fritz_callhistory") / "assets" / "icon.svg"
    return QIcon(str(icon_path))
