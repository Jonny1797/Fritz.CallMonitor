# Threading

## Never share a `sqlite3.Connection` across threads

Connections default to `check_same_thread=True` and raise `ProgrammingError` when touched from another thread. Any `QThread` worker that needs the DB must open its **own** connection via `db/connection.py`'s `connect()` (see the `sync_fn` closure in `app.py`, which also constructs `FritzBoxClient` inside the worker so login never blocks the GUI thread).

Failure mode is subtle: the exception is caught and shown as a status-bar message that vanishes after a few seconds — it looks like "nothing happened", not a crash.

## Closing a socket from another thread needs `shutdown()`

`CallMonitorConnection.close()` (called from the GUI thread via `CallMonitorThread.stop()`) must call `socket.shutdown(SHUT_RDWR)` before `close()`. `close()` alone only drops Python's fd refcount — the `makefile()` stream in the worker holds its own reference — so a thread blocked in `recv()` isn't reliably woken and the `QThread` outlives shutdown.
