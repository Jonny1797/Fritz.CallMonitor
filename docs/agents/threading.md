# Threading

## Never share a `sqlite3.Connection` across threads

Connections default to `check_same_thread=True` and raise `ProgrammingError` when touched from another thread. Any Background task that needs the DB must open its **own** connection via `db/connection.py`'s `connect()` (see `BoxGateway` in `sync/box_gateway.py`).

Failure mode is subtle: the exception is caught and shown as a status-bar message that vanishes after a few seconds — it looks like "nothing happened", not a crash.

## Closing a socket from another thread needs `shutdown()`

`CallMonitorConnection.close()` (called from the GUI thread via `CallMonitorThread.stop()`) must call `socket.shutdown(SHUT_RDWR)` before `close()`. `close()` alone only drops Python's fd refcount — the `makefile()` stream in the worker holds its own reference — so a thread blocked in `recv()` isn't reliably woken and the `QThread` outlives shutdown.

## Start every Background task through `BackgroundTasks`

All one-shot Box requests (sync, dial, Box import, phonebook list, voicemail, credentials check) run via `gui/background_tasks.py`'s `BackgroundTasks` (`MainWindow` owns the app's instance and hands it to views and dialogs; only `app.py`'s first-start credentials dialog uses its own short-lived instance): `start(fn, context, on_success, on_error, key=None)`. It owns the running-task list, refuses a second task with the same key, refuses starts and skips callbacks once quitting has begun, drops results of destroyed contexts, and waits for running tasks on quit (with a forced-exit failsafe). Do **not** create your own `QThread` for these and do not keep thread attributes on widgets. The call monitor is the exception and keeps its own stop protocol (see the socket section above).

## Box gateway: new client and own DB connection per operation

`BoxGateway` (`sync/box_gateway.py`) is what Background tasks run. Every operation takes a snapshot of the config and the keyring password when it starts, builds a **new** `FritzBoxClient` (none is kept between operations; fritzconnection makes no thread-safety promise) and, if it touches the DB, opens its **own** SQLite connection and closes it before returning. `apply_config()` swaps the config reference, so a running operation finishes with its old snapshot. Without credentials every operation raises `FritzBoxAuthError`; GUI code checks `gateway.has_credentials` at the moment it needs it instead of being told when credentials change. `has_credentials` is cached and never touches the keyring (a slow or locked Secret Service must not stall the GUI thread); `apply_config()` re-reads it, so call it **after** saving a new password.
