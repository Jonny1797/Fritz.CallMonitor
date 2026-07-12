# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.10.0] - 2026-07-12

### Added

- Telefonbuch-Import: CSV-Dateien aus gängigen Adressbuch-Exportformaten
  (ein Kontakt pro Zeile, Semikolon-getrennt, Spalten wie "Last Name",
  "First Name", "Company", "Home"/"Mobile"/"Business"/"Fax" etc.) werden
  jetzt zusätzlich zum bisherigen eigenen Export-Format erkannt und
  importiert.

### Fixed

- Telefonbuch-Import (CSV/vCard): Dateien mit cp1252/ISO-8859-1-Kodierung
  (z.B. Exporte aus jAnrufmonitor oder älteren Windows-Adressbüchern)
  führten zu einem Absturz (`UnicodeDecodeError`) statt einer Fehlermeldung;
  werden jetzt automatisch per Fallback korrekt gelesen.

## [0.9.0] - 2026-07-11

### Added

- Forgejo and GitHub Actions release workflows: pushing a version tag now
  builds a Windows `.exe` and a Linux executable via PyInstaller and
  publishes them as a release on each remote, using
  `scripts/changelog_section.sh` to pull that version's changelog section
  as the release notes.

## [0.8.0] - 2026-07-11

### Added

- Search box (by name or number) in Alle Anrufe's ungrouped mode, matching
  the search already available in grouped mode. Combines with the active
  date/"neu verpasst" filter and also narrows live (ringing/connected) calls,
  without affecting the global unread-missed-calls badge.
- Tooltips on the "Datum" and "Dauer" column headers in the call tables (Alle
  Anrufe and the contact detail history), explaining that the Fritz!Box only
  reports call timestamps and durations with minute precision (no seconds).

### Changed

- Moved the Telefonbuch tab's "Importieren …", "Exportieren …" and "Von Box
  importieren …" buttons into a new "Telefonbuch" menu in the menu bar,
  decluttering the tab's button row (now just Neu/Bearbeiten/Löschen).
- Moved "Jetzt synchronisieren" from a standalone button into the "Datei"
  menu (shortcut: F5).
- "Gruppieren" toggle in Alle Anrufe: now lines up with the content below it,
  no longer looks stuck in a pressed state, and its label switches to
  "Gruppierung aufheben" while active.
- Grouped view: the left contact table is narrower (1/3 instead of 2/3 of
  the available width) and no longer shows a redundant "Nummer" column,
  since the number is already shown in the right-hand call history once a
  contact is selected.
- The search boxes in Alle Anrufe's grouped and ungrouped modes now share
  their text: typing in one mirrors into the other, so switching the
  "Gruppieren" toggle no longer resets or duplicates what you were searching
  for.
- Every place a phone number is shown as text (contact call history, Alle
  Anrufe, Anrufbeantworter, Telefonbuch, the "Anrufen: …" context menu, the
  incoming-call tray/popup, and dial status-bar messages) now uses the same
  human-readable `+49 176 12345678`-style spacing instead of a mix of raw
  and unformatted numbers. Dialing, the phonebook, and search still use the
  unformatted number underneath - only the displayed text changed.

### Fixed

- Grouped mode's contact call history ("Nummer" column) showed the Fritz!Box's
  raw national-format number (e.g. `0176123456`) instead of the `+49…`
  formatting used everywhere else.
- Searching Alle Anrufe or the grouped contact list by a number's national
  form (e.g. `0176…`) found nothing, since numbers are stored in E.164
  (`+49176…`); the search now also matches national (leading `0`) and
  `00`-international queries against the stored number.

## [0.7.0] - 2026-07-11

### Changed

- Merged the "Kontakte" tab into "Alle Anrufe": a "Gruppieren" toggle now switches
  the same tab between the flat, chronological call list and the previous
  Kontakte view (search, per-contact detail panel with call history). Kontakte
  never held any data of its own — every row came from the calls table, grouped
  by number — so the merge drops no functionality and takes the app from four
  tabs to three (Alle Anrufe, Anrufbeantworter, Telefonbuch).

## [0.6.0] - 2026-07-10

### Added

- Settings dialog (Datei → Einstellungen…) for the sync interval, which phonebooks to
  include, and the incoming-call popup toggle — previously only editable by hand-editing
  the TOML config file. Changes are saved immediately but require an app restart to take
  effect, since the sync interval and phonebook selection are still wired up only once at
  startup.

## [0.5.1] - 2026-07-09

### Changed

- Replaced ASCII Umlaut workarounds (`ae`/`oe`/`ue`) with real Umlaute (`ä`/`ö`/`ü`) throughout
  comments, docstrings, and string literals in `src/` and `tests/`.

## [0.5.0] - 2026-07-09

### Added

- Real deletion of Anrufbeantworter messages: the "Löschen" button calls the Fritz!Box's
  `DeleteMessage` action directly, replacing the old local-only "Ausblenden".

### Changed

- Anrufbeantworter tab redesign: a visible action row (Abspielen/Anrufen/Gelesen/Löschen,
  each enabled only when applicable to the current selection) replaces the right-click
  context menu, and the player moved to the bottom of the tab. The seek bar now jumps to
  the clicked position instead of only reacting to dragging the handle. "Ausblenden" is
  gone — deleting a message removes it for real, and playing/marking a message read now
  clears its unread styling immediately instead of waiting for the next sync. Sync now
  also prunes messages that were deleted on the box through another channel (e.g. a
  handset), so the local list stays in sync with the box's actual state.

### Fixed

- `voicemail_audio()` (the voicemail playback download) had no request timeout, unlike
  every other Fritz!Box network call — a stalled download could leave the Anrufbeantworter
  tab stuck on "Lade Nachricht …" indefinitely instead of surfacing a connection error.

## [0.4.0] - 2026-07-09

### Added

- New "Anrufbeantworter" tab: lists the Fritz!Box's answering-machine messages (via the
  `X_AVM-DE_TAM` TR-064 service), with in-app playback (right-click "Abspielen" or
  double-click a row), "Anrufen" to call back, and "Ausblenden" to hide a message locally
  (the message itself stays on the box; this is a local-only "delete" by design). New/unheard
  messages are shown bold and red, mirroring the box's own read state; playing a message marks
  it read on the box too, which shows up after the next sync.

## [0.3.0] - 2026-07-08

### Added

- Click-to-dial: right-click a phone number in the Kontakte, Alle Anrufe, or contact-detail
  views and choose "Anrufen" to dial it via the Fritz!Box's Wählhilfe (rings a connected
  handset).
- Click-to-dial now also works on the Telefonbuch tab: right-click a contact with one stored
  number to dial it directly, or with several numbers to pick one from a submenu. Contacts with
  2+ numbers can optionally get a user-set "Standardnummer" (a radio button per number row in
  the edit dialog), which then dials directly from a top-level context-menu entry instead of
  requiring the submenu.

## [0.2.0] - 2026-07-08

### Changed

- "Alle Anrufe" is now the first tab (before "Kontakte"), since it's the app's main feature.

### Added

- Sync with the Fritz!Box now runs automatically on startup, not just on manual trigger.
- Bigger, always-on-top incoming-call popup alongside the tray notification, showing the
  caller's contact notes and a "Kontakt anzeigen" action; toggleable via the new
  `show_incoming_call_popup` config option (default on).

### Fixed

- Quitting the app while a sync (or other background `QThread`) was still running could
  hang or crash with `SIGABRT`; threads are now properly stopped before the app exits.

## [0.1.0] - 2026-07-03

### Added

- Initial release: searchable call list synced from a Fritz!Box (TR-064) into a local
  SQLite database, with per-contact interaction history.
- Live incoming-call notifications via the Fritz!Box call monitor (port 1012).
- "Alle Anrufe" view with date filtering and click-to-contact navigation.
- Missed-call tracking and call-type icons.
- Local phone book with import/export and Fritz!Box sync.
- Double-click-to-phonebook from the Kontakte and Alle Anrufe tabs.
- UI cleanup: consistent table heights, date formatting, sorting, and click behavior.

### Fixed

- Cross-thread SQLite connection bug in the live call-notification worker.
- Devices reporting as `-1` now display correctly.
