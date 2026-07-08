# Feature ideas (2026-07-07)

Brainstormed after reviewing the current app plus competitors (FRITZ!App Fon,
Truecaller/Hiya, tellows). Not planned/committed to yet — a list to pick from.

## Quick wins (reuse existing TR-064 plumbing)

- **Dial a specific number for Telefonbuch contacts with several numbers** —
  click-to-dial (right-click "Anrufen", shipped 2026-07-08) only covers
  Kontakte/Alle Anrufe/contact-detail, where each row has exactly one number.
  The Telefonbuch tab's contact table collapses multiple stored numbers into
  one joined display string per row, so it was deliberately left out of that
  pass — needs a way to pick which one to call (e.g. a small submenu) instead
  of guessing.
- **Surface phonebook notes more prominently** — `notes` field already
  exists per local contact (`ContactEditDialog`). Also revisit the deferred
  backlog item from the missed-calls work: a per-contact "recent call
  outcomes" icon-strip in the Kontakte tab.

## Higher-effort, high-value

- **Voicemail / Anrufbeantworter (TAM) integration** — TR-064 exposes the
  box's answering-machine messages; list/play/delete in-app instead of
  needing the box's own web UI. Mirrors what FRITZ!App Fon does.
- **Call statistics dashboard** — busiest callers, calls/day trend, total
  talk time, missed-call rate over time. Data already in `calls` table;
  pure GUI addition (use the dataviz skill when building this).
- **"Call back" flag** — lightweight checkbox on missed calls/contacts
  ("needs follow-up"); the app already functions as a mini-CRM for callers.
- **Hang-up control** — end a call in progress from the app.
  `fritzconnection.lib.fritzcall.FritzCall.hangup()` (same class as the
  `.dial()` click-to-dial now uses, wraps `X_AVM-DE_DialHangup`) takes no
  target argument - it just ends whatever the box's Wählhilfe channel is
  currently doing, so it'd be a `FritzBoxClient.hang_up()` method symmetric to
  `dial_number()`. Still needs a UI affordance, e.g. an "Auflegen" button
  shown only while `AllCallsView` is tracking a live (ringing/connected) call.

## Opt-in, privacy tradeoff

- **Reverse lookup / spam score for unknown numbers** via tellows' API
  (community-driven, DE-focused). Useful against spam calls, but means
  sending caller numbers to a third party. Given the app's local-only /
  keyring-based design so far, this should be an explicit opt-in setting,
  off by default — not a default-on integration.

## Polish / ease of operation

- Backup/restore or "export DB + config" for moving to a new PC.
- Keyboard shortcuts (e.g. `/` to focus search, `Ctrl+D` to dial selected
  contact).
- A settings dialog instead of hand-editing the TOML config for sync
  interval / phonebook IDs.
