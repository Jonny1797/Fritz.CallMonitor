# Fritz!Box integration

## TR-064 client (`fritz/client.py`)

- `FritzBoxClient` translates all `fritzconnection` / `requests` exceptions into `FritzBoxAuthError` / `FritzBoxConnectionError` / `FritzBoxPermissionError` (`fritz/exceptions.py`).
- Transient connection errors get one retry via `_retry_network`; auth/permission errors are never retried.

## Call monitor (`fritz/callmonitor.py` + `gui/callmonitor_worker.py`)

- Separate from TR-064: line-based TCP on port 1012 streaming `RING` / `CALL` / `CONNECT` / `DISCONNECT`.
- Requires dial code `#96*5*` once from a connected phone. Without it, connections are refused — handled by `CallMonitorThread`'s reconnect loop, not an error dialog.
- On `RING`, `MainWindow` shows a tray notification + `IncomingCallPopup`, resolving the name via the standard lookup path (see [architecture.md](architecture.md)).
- Thread shutdown: see [threading.md](threading.md).

## Box-side prerequisites (not app bugs if missing)

- TR-064 enabled: *Heimnetz > Netzwerk > Netzwerkeinstellungen > "Zugriff für Anwendungen zulässig"*.
- The configured user needs the right *"Sprachnachrichten, Fax, Anrufliste und FRITZ!App Fon"* — otherwise login succeeds but `GetCallList` raises `FritzBoxPermissionError`.

## Live test against a real box

```bash
FRITZ_ADDRESS=… FRITZ_USER=… uv run python scripts/check_connection.py   # prompts for password
```
