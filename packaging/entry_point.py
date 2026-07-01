"""Eigenständiger Einstiegspunkt für PyInstaller (Analysis braucht ein Top-Level-Skript)."""

from fritz_callhistory.app import main

if __name__ == "__main__":
    raise SystemExit(main())
