# Packaging (PyInstaller)

```bash
uv run pyinstaller packaging/fritz_callhistory.spec   # onefile build into dist/
```

`packaging/fritz_callhistory.spec` needs two non-obvious extras:

- `db/migrations/*.sql` as `datas` — loaded at runtime via `importlib.resources`; without them the frozen app starts with no schema.
- `keyring` backend modules as `hiddenimports` — its runtime backend discovery is invisible to PyInstaller's static analysis.

`packaging/entry_point.py` exists only because `Analysis()` needs a standalone top-level script, not `app.py`'s package-relative imports.
