# Architecture & layering

Package: `src/fritz_callhistory/`.

| Module | Role |
|---|---|
| `fritz/client.py` | Thin wrapper around `fritzconnection` (TR-064). See [fritzbox.md](fritzbox.md). |
| `fritz/callmonitor.py` | Raw TCP call-monitor protocol (port 1012). See [fritzbox.md](fritzbox.md). |
| `sync/` | Bridges `fritz/` and `db/`. `normalize.py` (phone numbers), `service.py` (`SyncService.sync_calls()` / `sync_phonebook()`), `phonebook_io.py`. |
| `db/` | Raw `sqlite3` + repository pattern in `db/repository.py`. No ORM. See [database.md](database.md). |
| `gui/` | PySide6 widgets, table models (`gui/models.py`), `QThread` workers (`gui/workers.py`, `gui/callmonitor_worker.py`). |
| `app.py` | Entry point; builds the `sync_fn` closure run by `SyncWorker`. See [threading.md](threading.md). |
| `credentials.py` / `config.py` / `paths.py` | Password in OS keyring; everything else in a TOML file under a `platformdirs` path. |

## Layering rules

- `gui/` **never calls `FritzBoxClient` (TR-064) directly** — network work goes through closures built in `app.py` and run in `QThread` workers.
- `gui/` may use: `db/` repositories, pure helpers from `sync/` (`normalize`, `phonebook_io`, `service.resolve_contact_names`), `fritz.exceptions`, and the call monitor via `gui/callmonitor_worker.py`.
- Nothing above `fritz/` imports `fritzconnection` or catches its/`requests`' exceptions — `fritz/client.py` translates them into `fritz/exceptions.py` types.
- Caller-name lookup (call list, incoming-call notifications) always goes through `normalize_number()` + the repositories' `find_by_number()` (`ContactRepository`, `LocalPhonebookRepository`) — don't add a separate matching path.

## Conventions

- Search is debounced (`install_debounced_search` in `gui/models.py`) and filtered SQL-side with `LIKE` in the repositories, not in a Qt proxy.
- **Never put the Fritz!Box password in the config file** — keyring only (`credentials.py`).
