# Feature ideas (2026-07-07)

Brainstormed after reviewing the current app plus competitors (FRITZ!App Fon,
Truecaller/Hiya, tellows). Not planned/committed to yet — a list to pick from.

## Quick wins (reuse existing TR-064 plumbing)

- **Click-to-dial ("Wählhilfe")** — `fritzconnection`'s `FritzCall` already
  exposes `dial_number`/`call_number` (`X_AVM-DE_OnTel`), the same service
  `fritz/client.py` already talks to for phonebook sync. Right-click a
  contact/number → dial via the box, handset rings, pick up. Small addition
  given the existing client layer. **Top pick for "next thing".**
- **Bigger incoming-call popup with actions**, not just the tray toast —
  `RING` parsing + caller-name resolution already exist
  (`MainWindow._on_ring`); a small always-on-top window (shows notes, more
  reliable than tray notifications some OSes suppress) would build on that.
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
