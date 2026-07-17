# Code improvement findings (2026-07-14)

From a full read-through of `src/fritz_callhistory/` (plus `packaging/entry_point.py`
and `scripts/check_connection.py`) looking for readability, performance, and
best-practice issues.

Of the original six findings, five were implemented (see `CHANGELOG.md` and
git history for what changed and why). One is left open — it needs a real-box
test rather than an unattended pass — and is tracked below.

## Manual query-string parsing in `voicemail_audio` — worth a second look, not a clear win

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
