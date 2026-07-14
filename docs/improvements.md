# Code improvement findings (2026-07-14)

From a full read-through of `src/fritz_callhistory/` (plus `packaging/entry_point.py`
and `scripts/check_connection.py`) looking for readability, performance, and
best-practice issues. Ordered by impact.

Items 1, 2, 3, and 6 were implemented on 2026-07-14. Items 4 and 5 are left open —
both need a deliberate trade-off call or a real-box test rather than an unattended
pass (see their entries below).

## 1. `LocalPhonebookRepository.list_all` is N+1 — done

Fixed: `list_all` now fetches all matching contacts and their numbers via a single
`LEFT JOIN` query, grouped into `LocalPhonebookContact` objects in Python, instead
of one query for ids plus two more per contact via `_load()`. See
`src/fritz_callhistory/db/repository.py`'s `LocalPhonebookRepository.list_all`.

## 2. Exception-translation duplication in `FritzBoxClient` — done

Fixed: added a `_translate_errors(permission_message=None)` decorator in
`src/fritz_callhistory/fritz/client.py` that collapses the repeated
`try/except FritzAuthorizationError / except _NETWORK_EXCEPTIONS` block, applied
to all `FritzBoxClient` methods except `__init__` (which raises `FritzBoxAuthError`
instead and doesn't fit the decorator's shape).

## 3. `QThread` worker boilerplate in `gui/workers.py` — done

Fixed: added a `_SimpleWorker` base class in `src/fritz_callhistory/gui/workers.py`
that collapses the repeated `run()` tail, used by `DialWorker`,
`VoicemailActionWorker`, `PhonebookListWorker`, `VoicemailAudioWorker`, and
`ImportFromBoxWorker`. `SyncWorker` and `CredentialsTestWorker` kept their own
`run()` as planned, since they branch into multiple distinct signals.

## 4. Per-row commits in the sync loop — real, but a documented trade-off

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

## 5. Manual query-string parsing in `voicemail_audio` — worth a second look, not a clear win

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

## 6. Minor: near-duplicate `set_search_text`/`focus_search` across views — done

Fixed: added `focus_search_edit`/`set_search_text_silently` free functions to
`src/fritz_callhistory/gui/models.py` (alongside `install_debounced_search`),
used by `contacts_view.py`, `all_calls_view.py` (both helpers), and
`phonebook_view.py` (`focus_search_edit` only). `voicemail_view.py`'s
`focus_search` stays as-is — it's a no-op stub, not a duplicate.

## Reviewed, no findings

`app.py`, `config.py`, `credentials.py`, `paths.py`, `db/connection.py`,
`db/schema.py`, `sync/normalize.py`, `sync/phonebook_io.py`,
`fritz/exceptions.py`, `fritz/callmonitor.py`, `gui/main_window.py`,
`gui/calls_tab.py`, `gui/contact_detail.py`, `gui/contact_edit_dialog.py`,
`gui/phonebook_picker_dialog.py`, `gui/credentials_dialog.py`,
`gui/settings_dialog.py`, `gui/incoming_call_popup.py`, `gui/icon.py`,
`gui/callmonitor_worker.py`, `packaging/entry_point.py`,
`scripts/check_connection.py`.
