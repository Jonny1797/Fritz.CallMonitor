# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
