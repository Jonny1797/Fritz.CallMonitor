"""Eigene Fehlertypen für den Fritz!Box-Zugriff (übersetzt fritzconnection/requests-Fehler)."""

from __future__ import annotations


class FritzBoxError(Exception):
    """Basisklasse für Fehler beim Zugriff auf die Fritz!Box."""


class FritzBoxAuthError(FritzBoxError):
    """Login (Benutzername/Passwort) fehlgeschlagen."""


class FritzBoxConnectionError(FritzBoxError):
    """Box nicht erreichbar (Netzwerk, falsche Adresse, TR-064 nicht aktiviert)."""


class FritzBoxPermissionError(FritzBoxError):
    """Benutzer hat nicht die nötigen Rechte (z.B. für die Anrufliste)."""
