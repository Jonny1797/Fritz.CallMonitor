# Architecture & layering

Package: `src/fritz_callhistory/`.

| Module | Role |
|---|---|
| `fritz/client.py` | Thin wrapper around `fritzconnection` (TR-064). See [fritzbox.md](fritzbox.md). |
| `fritz/callmonitor.py` | Raw TCP call-monitor protocol (port 1012). See [fritzbox.md](fritzbox.md). |
| `sync/` | Bridges `fritz/` and `db/`. `normalize.py` (phone numbers), `service.py` (`SyncService.sync_calls()` / `sync_phonebook()`), `phonebook_io.py`, `caller_directory.py` (`CallerDirectory`: who is behind a number), `box_gateway.py` (`BoxGateway`: the app's one way to act on the Fritz!Box with the stored login). |
| `db/` | Raw `sqlite3` + repository pattern in `db/repository.py`. No ORM. See [database.md](database.md). |
| `gui/` | PySide6 widgets, table models (`gui/models.py`), Background tasks (`gui/background_tasks.py`), call monitor thread (`gui/callmonitor_worker.py`). |
| `app.py` | Entry point; builds one `BoxGateway` and passes it to `MainWindow(connection, config, gateway)`. See [threading.md](threading.md). |
| `credentials.py` / `config.py` / `paths.py` | Password in OS keyring; everything else in a TOML file under a `platformdirs` path. |

## Layering rules

- `gui/` **never calls `FritzBoxClient` (TR-064) directly** — network work goes through the Box gateway (`sync/box_gateway.py`), run as a Background task via `BackgroundTasks`. Views and `CredentialsDialog` receive the gateway and check `gateway.has_credentials` when needed; `SettingsDialog` and `PhonebookPickerDialog` stay gateway-free — `MainWindow` loads the phonebook list for them and hands it over.
- `gui/` may use: `db/` repositories, pure helpers from `sync/` (`normalize`, `phonebook_io`, `caller_directory`, `box_gateway`), `fritz.exceptions`, and the call monitor via `gui/callmonitor_worker.py`.
- Nothing above `fritz/` imports `fritzconnection` or catches its/`requests`' exceptions — `fritz/client.py` translates them into `fritz/exceptions.py` types.
- Caller identity always comes from the Caller directory (`sync/caller_directory.py`) — don't add a separate matching path. (The Telefonbuch tab's "edit the contact that owns this number" via `find_by_number` is Telefonbuch editing, not identity.)

## Conventions

- Search is debounced (`install_debounced_search` in `gui/models.py`) and filtered SQL-side with `LIKE` in the repositories, not in a Qt proxy.
- **Never put the Fritz!Box password in the config file** — keyring only (`credentials.py`).
