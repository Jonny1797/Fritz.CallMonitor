# Feature ideas (2026-07-07)

Brainstormed after reviewing the current app plus competitors (FRITZ!App Fon,
Truecaller/Hiya, tellows). Not planned/committed to yet — a list to pick from.

## Quick wins (reuse existing TR-064 plumbing)

- **Surface phonebook notes more prominently** — `notes` field already
  exists per local contact (`ContactEditDialog`). Also revisit the deferred
  backlog item from the missed-calls work: a per-contact "recent call
  outcomes" icon-strip in the Kontakte tab.

## Higher-effort, high-value

- **Call statistics dashboard** — busiest callers, calls/day trend, total
  talk time, missed-call rate over time. Data already in `calls` table;
  pure GUI addition (use the dataviz skill when building this).
- **"Call back" flag** — lightweight checkbox on missed calls/contacts
  ("needs follow-up"); the app already functions as a mini-CRM for callers.
- **Hang-up control** — end a call in progress from the app.
  `fritzconnection.lib.fritzcall.FritzCall.hangup()` (same class as the
  `.dial()` click-to-dial now uses, wraps `X_AVM-DE_DialHangup`) takes no
  target argument - it just ends whatever the box's Wählhilfe channel is
  currently dialing a
  specific one of several numbers doing, so it'd be a `FritzBoxClient.hang_up()` method symmetric to
  `dial_number()`. Still needs a UI affordance, e.g. an "Auflegen" button
  shown only while `AllCallsView` is tracking a live (ringing/connected) call.

## Opt-in, privacy tradeoff

- **Reverse lookup / spam score for unknown numbers** via tellows' API
  (community-driven, DE-focused). Useful against spam calls, but means
  sending caller numbers to a third party. Given the app's local-only /
  keyring-based design so far, this should be an explicit opt-in setting,
  off by default — not a default-on integration.

## Polish / ease of operation

- **"Clear default number" affordance for Telefonbuch contacts** — the
  per-number "Standard" radio in `ContactEditDialog` (shipped alongside
  Telefonbuch click-to-dial, 2026-07-08) uses a standard exclusive
  `QButtonGroup`, which has no built-in "uncheck all" interaction. Right now
  the only way back to "no default" is removing and re-adding the row. Fine
  for now (not asked for), but a real fix would need e.g. click-to-toggle-off
  (temporarily disabling group exclusivity around the click) or an explicit
  "Kein Standard" option.
- Backup/restore or "export DB + config" for moving to a new PC.
- Keyboard shortcuts (e.g. `/` to focus search, `Ctrl+D` to dial selected
  contact).
- **Edit Fritz!Box connection details after first run** — the settings
  dialog (Datei → Einstellungen…, shipped 2026-07-10) deliberately left
  address/username/password out of scope; those still only get set once via
  `CredentialsDialog`, which is only ever shown on first run (missing/invalid
  stored credentials). Right now the only way to change the box address, the
  Fritz!Box user, or rotate the password is to edit the TOML config /
  keyring by hand or delete them so `CredentialsDialog` reappears. Folding
  connection-details editing into the settings dialog (or reusing
  `CredentialsDialog` from a menu entry) would close that gap — would also
  need a "test connection" affordance, since a bad address/password here
  isn't caught until the next sync.
- **Apply settings changes without restarting** — the new settings dialog
  saves `sync_interval_minutes`/`phonebook_ids`/`show_incoming_call_popup`
  straight to the TOML config, but none of them take effect until the app is
  restarted: the auto-sync `QTimer` interval and the phonebook IDs baked into
  `sync_fn`'s closure (`app.py`) are both set up once at startup, with no
  runtime-reconfiguration plumbing today. A real fix needs a setter on
  `MainWindow` for the timer interval and a way to rebuild/replace the
  `sync_fn`/`import_from_box_fn` closures when phonebook IDs change.
- **Phonebook picker has no offline fallback** — the settings dialog's
  Telefonbücher picker needs a live box connection to fetch phonebook names
  (`FritzBoxClient.phonebooks()`); if that fails or no credentials are
  stored, the whole picker is disabled and `phonebook_ids` can't be changed
  at all until connectivity is restored — even though the user might know
  the numeric IDs already. A fallback manual-entry field (comma-separated
  IDs, skipping the name lookup) would cover that case.
