# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für fritz-callhistory.

Baut eine windowed (konsolenlose) Executable, u.a. für Windows.
Aufruf: uv run pyinstaller packaging/fritz_callhistory.spec
"""

import pathlib

project_root = pathlib.Path(SPECPATH).resolve().parent  # noqa: F821 (von PyInstaller injiziert)
src_dir = project_root / "src"
migrations_dir = src_dir / "fritz_callhistory" / "db" / "migrations"

# db/schema.py liest die Migrationsdateien zur Laufzeit über importlib.resources -
# ohne diesen Eintrag würde die gefrorene .exe mit einer leeren Datenbank starten.
datas = [(str(p), "fritz_callhistory/db/migrations") for p in migrations_dir.glob("*.sql")]

a = Analysis(  # noqa: F821
    [str(project_root / "packaging" / "entry_point.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    # keyring wählt sein Backend zur Laufzeit über Entry Points/Introspektion -
    # PyInstaller findet das nicht immer automatisch, daher explizit auflisten.
    hiddenimports=[
        "keyring.backends.Windows",
        "keyring.backends.macOS",
        "keyring.backends.SecretService",
        "keyring.backends.chainer",
        "keyring.backends.libsecret",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="fritz-callhistory.exe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
