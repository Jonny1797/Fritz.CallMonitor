# Code improvement findings (2026-07-14)

From a full read-through of `src/fritz_callhistory/` (plus `packaging/entry_point.py`
and `scripts/check_connection.py`) looking for readability, performance, and
best-practice issues. Not planned/committed to yet — a list to pick from.
Ordered by impact.

## 1. `resolve_contact_names` re-queries the DB per contact, on a hot path

`src/fritz_callhistory/sync/service.py:43-64`

Runs on every sync and after every local phonebook edit (`gui/phonebook_view.py`'s
`_after_local_change`). For each contact it fires two `lookup_name` SELECTs (local
+ box phonebook) and, on a name change, a separate commit via `set_display_name`.
For N contacts that's up to 3N round-trips + up to N commits, every time — the
hottest instance of the "repeated queries in a loop" pattern in this codebase.

Fix direction: load both phonebooks into `dict[number_normalized, name]` once (two
queries total instead of 2N), then do a single in-memory pass, and batch the
`display_name` updates into one transaction. Needs new bulk-fetch methods on
`PhonebookRepository`/`LocalPhonebookRepository` (currently only single-lookup
`lookup_name` exists).

## 2. `LocalPhonebookRepository.list_all` is N+1

`src/fritz_callhistory/db/repository.py:367-373`

```python
def list_all(self, query: str = "") -> list[LocalPhonebookContact]:
    pattern = f"%{query}%"
    rows = self._conn.execute(
        "SELECT id FROM phonebook_contacts WHERE display_name LIKE ? ORDER BY display_name",
        (pattern,),
    ).fetchall()
    return [self._load(row["id"]) for row in rows]
```

`_load()` (line 533) issues two more queries per contact (contact row + numbers).
This backs the always-visible "Telefonbuch" tab, so it runs on every
reload/search keystroke (debounced, but still). Fix: fetch all matching contacts
and all their numbers in two queries, then group numbers by
`phonebook_contact_id` in Python before constructing `LocalPhonebookContact`
objects — same shape as `CallRepository.all_calls`'s single-JOIN approach used
elsewhere in this file.

## 3. Exception-translation duplication in `FritzBoxClient`

`src/fritz_callhistory/fritz/client.py` (repeated ~7 times, e.g. lines 208-217,
219-229, 255-270, 278-300, 302-326, 328-348, 350-370)

Every method wraps its `_retry_network(...)` call in the same three-way
`try/except FritzAuthorizationError / except _NETWORK_EXCEPTIONS` translation.
This is the most repeated block in the codebase and is easy to get subtly wrong
on the next new method (e.g. forgetting the permission message). A decorator
would collapse it:

```python
def _translate_errors(permission_message: str | None = None):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except FritzAuthorizationError as exc:
                if permission_message:
                    raise FritzBoxPermissionError(permission_message) from exc
                raise
            except _NETWORK_EXCEPTIONS as exc:
                raise FritzBoxConnectionError(str(exc)) from exc
        return wrapper
    return decorator
```

Methods without a permission-specific message (e.g. `phonebook_ids`,
`phonebook_contacts_detailed`) would just omit the argument.

## 4. `QThread` worker boilerplate in `gui/workers.py`

`src/fritz_callhistory/gui/workers.py` (all six worker classes, e.g. lines
38-50, 66-75, 91-100, 116-125, 140-149, 165-174)

Each worker's `run()` repeats the same `except FritzBoxError / except Exception`
tail with a different final signal name. The classes genuinely differ enough
(differing signal signatures, `SyncWorker` splitting out `auth_failed`,
`CredentialsTestWorker` having 4 branches) that collapsing them into one generic
class isn't a clean win — but the common tail is worth extracting into a small
base class that `DialWorker`, `VoicemailActionWorker`, `PhonebookListWorker`,
`VoicemailAudioWorker`, and `ImportFromBoxWorker` could use directly;
`SyncWorker` and `CredentialsTestWorker` would keep their own `run()`.

## 5. Per-row commits in the sync loop — real, but a documented trade-off

`src/fritz_callhistory/db/repository.py` — `ContactRepository.upsert` (line 92),
`CallRepository.insert` (line 197), `VoicemailRepository.insert_or_update`
(line 645)

`SyncService.sync_calls`/`sync_voicemail` (`sync/service.py:84-146`) call these
once per remote call/message, and each call commits individually — for a sync of
a few hundred calls that's a few hundred separate commits. Not a free-lunch fix
though: `app.py`'s SIGINT/`os._exit` handling explicitly relies on "every DB
write commits individually" so a hard kill loses at most one write (see
`_handle_sigint` and the `os._exit(exit_code)` comment in `app.py:332-406`).
Sync is idempotent and safely re-runnable, so a batched-commit fast path
specific to `SyncService` (wrap the per-call loop in one transaction, leave the
interactive GUI-facing repo methods as-is) is defensible, but should be
introduced deliberately with that trade-off in mind rather than as a blanket
"remove per-op commits" change.

## 6. Manual query-string parsing in `voicemail_audio` — worth a second look, not a clear win

`src/fritz_callhistory/fritz/client.py:314-315`

```python
query = path.split("?", 1)[1] if "?" in path else path
params = dict(pair.split("=", 1) for pair in query.split("&") if "=" in pair)
```

`urllib.parse.parse_qsl(query)` is the idiomatic replacement and handles edge
cases (repeated keys, `+`/percent-decoding) this hand-rolled split doesn't.
However, `parse_qsl` would URL-*decode* values that the current code passes
through raw — if `call_url()` re-encodes its `params` dict before building the
request, switching parsers could change what's sent. Worth trying only with a
test against a real box's `download.lua` path.

## 7. Minor: near-duplicate `set_search_text`/`focus_search` across views

`src/fritz_callhistory/gui/contacts_view.py:116-128`,
`src/fritz_callhistory/gui/all_calls_view.py:234-246`

Both `set_search_text` methods are near-verbatim (block signals, set text,
unblock, stop debounce timer), and `focus_search` (set focus + select-all)
repeats across `contacts_view.py`, `all_calls_view.py`, and `phonebook_view.py`.
Given the two views are deliberately kept independent/testable, this is minor —
a shared free function in `gui/models.py` (alongside `install_debounced_search`)
would remove the duplication without coupling the views to each other.

## Reviewed, no findings

`app.py`, `config.py`, `credentials.py`, `paths.py`, `db/connection.py`,
`db/schema.py`, `sync/normalize.py`, `sync/phonebook_io.py`,
`fritz/exceptions.py`, `fritz/callmonitor.py`, `gui/main_window.py`,
`gui/calls_tab.py`, `gui/contact_detail.py`, `gui/contact_edit_dialog.py`,
`gui/phonebook_picker_dialog.py`, `gui/credentials_dialog.py`,
`gui/settings_dialog.py`, `gui/incoming_call_popup.py`, `gui/icon.py`,
`gui/callmonitor_worker.py`, `packaging/entry_point.py`,
`scripts/check_connection.py`.
