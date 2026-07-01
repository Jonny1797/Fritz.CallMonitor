# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A PySide6 desktop app that connects to an AVM Fritz!Box (TR-064) and shows a searchable call list (by name/number) plus the interaction history per contact. It syncs the box's call list into a local SQLite database so history outlives the box's own limited retention.

## Commands

```bash
uv sync                                    # install/update deps into .venv
uv run fritz-callhistory                   # start the GUI app
uv run python scripts/check_connection.py  # isolated CLI test against a real box (needs FRITZ_ADDRESS/FRITZ_USER env vars; prompts for password)
uv run pytest                              # full test suite
uv run pytest tests/test_sync_service.py               # single file
uv run pytest tests/test_sync_service.py::test_sync_is_idempotent_on_repeated_run  # single test
uv run ruff check .                        # lint (line-length 100, see [tool.ruff] in pyproject.toml)
uv run pyinstaller packaging/fritz_callhistory.spec     # build a onefile executable into dist/
```

GUI tests use `pytest-qt`. `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` before PySide6 is imported, so tests run headless without an X server automatically.

## Architecture

Strict layering, each layer only talks to the one below it:

- **`fritz/client.py`** — thin wrapper around `fritzconnection` (TR-064). `FritzBoxClient` translates all `fritzconnection`/`requests` exceptions into `fritz/exceptions.py`'s `FritzBoxAuthError` / `FritzBoxConnectionError` / `FritzBoxPermissionError`, so nothing above this layer needs to know about `fritzconnection` internals. Transient connection errors get one retry via `_retry_network`; auth/permission errors are never retried.
- **`sync/`** — bridges the Fritz!Box client and the database. `sync/normalize.py` normalizes numbers with `phonenumbers` (region `DE`); missing/suppressed numbers become the `ANONYMOUS_NUMBER` sentinel so they group into one pseudo-contact instead of creating duplicates. `sync/service.py`'s `SyncService.sync_calls()` / `sync_phonebook()` pull data via `FritzBoxClient` and write through the `db/` repositories.
- **`db/`** — no ORM, raw `sqlite3` + a repository pattern (`ContactRepository`, `CallRepository`, `PhonebookRepository`, `SyncStateRepository` in `db/repository.py`). Migrations are plain numbered `.sql` files in `db/migrations/`, applied via `PRAGMA user_version` tracking in `db/schema.py`.
- **`gui/`** — PySide6. Talks only to the `db/` repositories, never directly to `fritz/`. `gui/models.py` holds `QAbstractTableModel` subclasses (`ContactListModel`, `CallListModel`); `gui/main_window.py` wires the search box (debounced, SQL-side `LIKE`), table selection, and the detail panel (`gui/contact_detail.py`) together.
- **`app.py`** — entry point. Builds the `sync_fn` closure that `gui/workers.py`'s `SyncWorker` (a `QThread` subclass) runs in the background — `FritzBoxClient` is constructed *inside* that closure, and that closure opens its **own** `sqlite3` connection (see gotcha below), so the network/login round-trip never blocks the GUI thread.
- **Credentials/config**: the Fritz!Box password lives only in the OS keyring (`credentials.py`); everything else (address, username, sync interval, included phonebook IDs) is a TOML file under a `platformdirs` path (`paths.py`, `config.py`). Never put the password in the config file.
- **`fritz/callmonitor.py` + `gui/callmonitor_worker.py`** — live "incoming call" notifications, separate from TR-064/`fritzconnection` entirely: a raw line-based TCP protocol on port 1012 that the box streams `RING`/`CALL`/`CONNECT`/`DISCONNECT` events over. Requires the box's `#96*5*` dial code to be activated once from a connected phone; otherwise connecting just gets refused (handled via `CallMonitorThread`'s reconnect loop, not an error dialog). `MainWindow` shows a system-tray notification (`QSystemTrayIcon`) on `RING`, resolving the caller's name through the same `normalize_number()` + `ContactRepository.find_by_number()` path used elsewhere — no separate matching logic.

### Non-obvious gotchas worth knowing before touching the schema

- **Call type codes** (from the installed `fritzconnection` lib, not just its docs): `1`=received, `2`=missed, `3`=outgoing, `9`=active received, `10`=rejected, `11`=active outgoing.
- **Dedupe uses a `COALESCE`-based unique index, not a table-level `UNIQUE` constraint.** SQLite treats `NULL` as never-equal-to-`NULL` in `UNIQUE` constraints, and nullable fields (`caller_number`/`called_number`/`duration_seconds`) are common in real call data (e.g. missed calls have no duration). See `db/migrations/001_init.sql` (`idx_calls_dedupe`) — changing this back to a plain `UNIQUE(...)` will silently reintroduce duplicate rows on repeated syncs.
- **PyInstaller packaging needs two extra things beyond the obvious `Analysis()` call** (see `packaging/fritz_callhistory.spec`): the `db/migrations/*.sql` files must be added as `datas` (loaded at runtime via `importlib.resources`, otherwise the frozen app starts with an "empty" schema setup), and `keyring`'s backend modules must be listed as `hiddenimports` (its runtime backend discovery isn't picked up by PyInstaller's static analysis). `packaging/entry_point.py` exists only because `Analysis()` needs a standalone top-level script rather than `app.py`'s package-relative imports.
- **Never share a `sqlite3.Connection` across threads.** It defaults to `check_same_thread=True` and raises `ProgrammingError` if touched from another thread — any `QThread` worker that needs the database (see `SyncWorker`'s `sync_fn` in `app.py`) must open its own connection via `db/connection.py`'s `connect()`, not reuse the GUI thread's. The failure mode is subtle: the exception gets caught and shown as a status-bar message that disappears in a few seconds, so it looks like "nothing happened" rather than an obvious crash.
- **Closing a socket from another thread needs `shutdown()`, not just `close()`.** `CallMonitorConnection.close()` (called from the GUI thread via `CallMonitorThread.stop()`) must call `socket.shutdown(SHUT_RDWR)` before `close()` — `.close()` alone only decrements Python's internal fd refcount (the `makefile()`-derived stream in the worker thread holds its own reference) and won't reliably unblock a thread stuck in a blocking `recv()`, leaving the `QThread` running past shutdown.

### Fritz!Box-side prerequisites (not app bugs if missing)

- TR-064 access must be enabled: *Heimnetz > Netzwerk > Netzwerkeinstellungen > "Zugriff für Anwendungen zulässig"*.
- The configured Fritz!Box user needs the right *"Sprachnachrichten, Fax, Anrufliste und FRITZ!App Fon"* — without it, login succeeds but `GetCallList` fails (`FritzBoxPermissionError`).
