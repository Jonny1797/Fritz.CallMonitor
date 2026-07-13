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
- **Apply settings changes without restarting** — the new settings dialog
  saves `sync_interval_minutes`/`phonebook_ids`/`show_incoming_call_popup`
  straight to the TOML config, but none of them take effect until the app is
  restarted: the auto-sync `QTimer` interval and the phonebook IDs baked into
  `sync_fn`'s closure (`app.py`) are both set up once at startup, with no
  runtime-reconfiguration plumbing today. A real fix needs a setter on
  `MainWindow` for the timer interval and a way to rebuild/replace the
  `sync_fn`/`import_from_box_fn` closures when phonebook IDs change.
