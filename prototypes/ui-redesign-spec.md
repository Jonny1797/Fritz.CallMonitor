# Spec: Choosable main-window layouts "Drei Spalten" (A) and "Personen" (C)

Labels: `ready-for-agent`

Prototype (primary source, not for master): `prototypes/ui-mockup.prototype.html` on branch
`worktree-prototype-ui-mockup` (variants `#a` and `#c`; `#b` was rejected). Published preview:
https://claude.ai/artifact/U1LnZTZzLtEcBojGzvFgHT

## Problem Statement

The app today is a single window with three tabs ("Alle Anrufe", "Anrufbeantworter",
"Telefonbuch"). Everything works, but it's organized around data sources, not around how I use it:

- To see everything that happened with one person (calls on any of their numbers plus their
  voicemails), I have to switch between tabs, flip the "Gruppieren" toggle, and look at a call list
  that is grouped by **number**, not by person.
- "New" only exists for missed calls, as one global "seen" point in time. Opening a person doesn't
  make their entries count as seen.
- A running call shows up as a row inside the call list. That's easy to miss when I'm on another
  tab.
- I can't back up the local database (call history, voicemail metadata, local phonebook) from inside
  the app, even though keeping history longer than the box does is the reason the app exists.

## Solution

The main window offers two layouts. I pick one under "Einstellungen…", and switching takes effect
right away, without restarting:

- **"Drei Spalten" (A).** A navigation column on the left ("Anrufliste", "Anrufbeantworter",
  "Kontakte", "Sicherung & Import", with counts of unseen entries), a filterable list in the middle,
  and a detail pane on the right. The detail pane shows the selected person, an "Anrufen" button per
  number, the selected call or a voicemail player, and that person's full history. A running call
  shows as a green bar across the whole window.
- **"Personen" (C).** A sidebar listing people by most recent activity, with search, a type filter
  (Alle / Neu / Verpasst / AB), a date filter that narrows the **whole sidebar**, and a switch
  between "Personen" and "Chronik". On the right is the selected person's history as a chat-style
  thread: incoming calls on the left, outgoing calls on the right, missed and rejected calls as
  centered notes, voicemails as playable bubbles. A status bar at the bottom shows the connection,
  the last sync and "Aktualisieren". A running call shows as a floating card.

Both layouts share the same menus, tray icon, incoming-call popup, sync, call monitor, dialing,
contact editing and backup. Only the layout of the central area differs.

## User Stories

1. As a user, I want to choose between "Drei Spalten" and "Personen" under "Einstellungen…", so that the window fits how I work.
2. As a user, I want a layout change to take effect immediately without restarting, so that I can compare the two quickly.
3. As a user, I want my layout choice to be remembered across restarts, so that I don't have to pick it again.
4. As a new user, I want "Drei Spalten" as the default layout, so that the first start looks familiar after an update.
5. As a user, I want my search text and date filter to stay when I switch layouts, so that switching doesn't lose my place.
6. As a user, I want to search history by name or number (including "0171…" matching "+49 171…"), so that I find a person however I remember them.
7. As a user, I want to filter history by date range and by the quick choices Heute / Gestern / 7 Tage / 30 Tage / Alles, so that I can look at a specific period.
8. As a user of "Personen", I want the date filter to narrow the whole people list (people with no entries in the period disappear), so that the sidebar answers "who did I have contact with in that period?".
9. As a user, I want to filter by entry type (all / received / outgoing / missed / voicemail / only unseen), so that I can focus on what needs attention.
10. As a user, I want a visible "Filter aktiv" hint with one "Alle Filter zurücksetzen" action, so that I don't mistake a filtered list for missing data.
11. As a user, I want every entry to show the person (or number), the type with its own icon and color, the time and the duration, so that I can tell entries apart at a glance.
12. As a user, I want history grouped by **person** (a local phonebook contact with all of their numbers), not by single number, so that calls from someone's mobile and landline end up together.
13. As a user, I want numbers that aren't in my phonebook to appear as their own person (shown as the number), so that unknown callers still have a history.
14. As a user, I want all calls with a suppressed number grouped as one "Unbekannt" entry, so that they don't spread across the list.
15. As a user of "Drei Spalten", I want a "Nach Person gruppieren" switch in the call list, so that I can choose between a chronological list and one row per person.
16. As a user of "Personen", I want a "Chronik" mode in the sidebar, so that I can scan everything chronologically and still jump to a person's thread.
17. As a user, I want unseen entries highlighted (bold, tinted row or outlined bubble) and counted in the navigation, so that I notice what's new.
18. As a user, I want opening a person to mark all of their entries as seen, so that the highlight disappears once I've looked.
19. As a user, I want an "Alle als gesehen markieren" action, so that I can clear all highlights at once.
20. As a user, I want missed calls and new voicemails to count as unseen, and received or outgoing calls not to, so that "new" means "needs my attention".
21. As a user, I want a voicemail's "new" state to follow the Fritz!Box (played on a handset means no longer new after the next sync), so that the app and the box agree.
22. As a user, I want to play a voicemail inline (play/pause, seek, position/length), so that I don't need another tool.
23. As a user, I want playing a voicemail to mark it as read on the Fritz!Box and never delete it, so that listening is safe.
24. As a user, I want to delete a voicemail only through an explicit "Löschen" button with a confirmation that says it deletes on the Fritz!Box and can't be undone, so that I never lose a message by accident.
25. As a user, I want an "Anrufen" button for a person (one per number when there are several, for example "Mobil anrufen"), so that I can call back from the history.
26. As a user, I want "Anrufen" to use the box's dial help (my phone rings first) and to see a status message about it, so that I know what happens next.
27. As a user, I want no "Anrufen" button for suppressed numbers, so that I don't get an action that can't work.
28. As a user, I want to see a running call prominently (a bar in "Drei Spalten", a floating card in "Personen") with name, number and a ticking duration, so that I notice it whatever I'm looking at.
29. As a user, I want a click on the running-call display to open that person's history, so that I have context during the call.
30. As a user, I want the existing incoming-call popup (name, number, last contact) in both layouts, so that the alert doesn't depend on the layout.
31. As a user, I want to know that calls can't be answered from the app (display only), so that I don't look for an answer button.
32. As a user, I want "Aktualisieren" (and F5) visible in both layouts, with the time of the last sync and a busy state while syncing, so that I can force a refresh and see that it's running.
33. As a user, I want to see the connection state to the Fritz!Box in both layouts, so that I know whether the data is current.
34. As a user, I want to create a contact, so that a number gets a name.
35. As a user, I want "Als Kontakt speichern" on an unknown number, prefilled with that number, so that naming a caller takes one step.
36. As a user, I want to edit a contact (name, several numbers with type, note), so that my phonebook stays correct.
37. As a user, I want to delete a contact after a confirmation that says the history stays, so that I don't lose calls by deleting a name.
38. As a user, I want the contact form to say that changes stay in the app and don't change the Fritz!Box phonebook, so that I know what editing does.
39. As a user, I want contacts I delete to come back on the next import from the box (if they're still on the box), and I'm fine with that, so that the import stays a simple copy.
40. As a user of "Drei Spalten", I want to edit contacts inline in the detail pane, and as a user of "Personen" in a dialog opened from the thread header, so that editing fits each layout.
41. As a user, I want to import contacts from chosen Fritz!Box phonebooks, so that I don't type them in by hand.
42. As a user, I want the existing file import/export of the phonebook in both layouts, so that nothing goes missing.
43. As a user, I want "Jetzt sichern …" to save a complete copy of the local database to a file I choose, so that my history survives a broken disk or a reinstall.
44. As a user, I want to see when the last backup was made and how much it contained, so that I know whether I'm protected.
45. As a user, I want "Wiederherstellen …" to load a backup after a confirmation, refusing files that aren't a backup of this app or come from a newer app version, so that I can't break the database with the wrong file.
46. As a user, I want all views to refresh right after a restore, so that I see the restored data without restarting.
47. As a user, I want the backup and import functions under "Sicherung & Import" (a section in A, a dialog in C), so that they're easy to find in both layouts.
48. As a keyboard user, I want the existing shortcuts (/ and Ctrl+F for search, Ctrl+D to dial, F5 to sync, Ctrl+1…4 for sections in A) to keep working, so that the new layouts don't slow me down.
49. As a user, I want both layouts to follow the system light/dark theme, so that the app looks right on my desktop.
50. As a user, I want the window to stay responsive during sync, dialing, audio download and backup, so that the UI never freezes.

## Implementation Decisions

- **Layout setting.** `Config` gains a `layout` field with the values `"classic"` ("Drei Spalten") and `"people"` ("Personen"), default `"classic"`. Unknown values fall back to the default; the TOML loader already ignores unknown keys. `SettingsDialog` gets a choice for it.
- **One layout interface, two implementations.** `MainWindow` keeps everything that doesn't depend on the layout: menus, tray, call monitor, incoming-call popup, sync/dial/voicemail/import background tasks, the close/shutdown logic and the auto-sync timer. The central area is a layout widget behind a small shared interface that both layouts implement:
  - `reload()`, `focus_search()`, `dial_selected()`, `show_person(person_key)`
  - live call hooks matching today's: `on_live_ring(...)`, `on_live_connected(...)`, `on_live_disconnected(...)`, `clear_live_calls()`
  - `filter_state` (get/set), so search/date/type survive a layout switch
  - signals: `call_requested(number)`, `unseen_counts_changed(...)`, `live_call_ended()`, `backup_requested()`, `restore_requested()`
  
  `MainWindow` connects to the active layout only through this interface. Switching layouts builds the other widget, hands over `filter_state`, swaps the central widget and disconnects the old one. Running background tasks belong to `MainWindow`, so a switch never interrupts them.
- **New Qt-free history query module (the main new seam).** One module in `db/` (or `sync/`, next to `resolve_contact_names`) answers "people and their entries" for both layouts:
  - `people(filter) -> list[PersonSummary]`: key, display name, numbers, last activity, counts per type, unseen count; sorted by last activity.
  - `entries(filter, person_key=None) -> list[HistoryEntry]`: calls **and** voicemails merged and sorted by time.
  - `filter` holds search text, date range, type set, unseen-only.
  - **Person key**: a local phonebook contact id when one of their numbers matches (`LocalPhonebookRepository.find_by_number` / `all_names` semantics), otherwise the normalized number. `ANONYMOUS_NUMBER` is its own single person. This replaces "one contact per number" (`ContactRepository`) as the grouping unit in both new layouts. `ContactRepository` stays as the number index used by sync and name resolution.
  - Search matching reuses `normalize_number()` and stays SQL-side `LIKE` (see the architecture conventions); name lookups follow the existing `find_by_number()` path, with no new matching logic.
  - Entry types: received, outgoing, missed, rejected (codes 1/3/2/10), voicemail. Active codes 9/11 and the in-memory live pseudo types are never stored and never returned.
- **Unseen = per-person watermark (decided).** Keep the global `missed_calls_last_seen_at` in `sync_state` for "Alle als gesehen markieren". Add a per-person "seen until" timestamp in a new migration (a small table keyed by person key). A missed or rejected call is unseen if its `call_date` is later than both the global and the person's watermark. A voicemail is unseen while its box-authoritative `is_new` is set; opening a person also calls the existing mark-read path for their new voicemails. Opening a person sets their watermark to "now". There are no per-row seen flags, which keeps the earlier design decision.
- **Layout "Drei Spalten" (A).** The navigation column replaces the `QTabWidget`, with a `QStackedWidget` behind it. The "Anrufliste", "Anrufbeantworter" and "Kontakte" sections reuse today's `AllCallsView` / `GroupedContactsView` (inside `CallsTab`), `VoicemailView` and `PhonebookTab` where they fit, and gain the shared detail pane (person header with "Anrufen" buttons per number, selected call or voicemail player, person history). "Sicherung & Import" is a new panel. The running call is a bar across the window under the title area.
- **Layout "Personen" (C).** New widgets: a people sidebar (search, type filter, date quick choices plus from/to, "Personen"/"Chronik" switch, "Alle Filter zurücksetzen") and a thread view rendered from `entries(filter, person_key)`. The thread header has name, numbers, note, "Anrufen" per number, "Bearbeiten" (opens the existing `ContactEditDialog`) and "Löschen"; an unknown number gets "Als Kontakt speichern". The thread shows only a "Gefiltert: … · Filter zurücksetzen" note, not its own date inputs (decided in the prototype: the date filter lives in the sidebar). Status bar: connection, last sync, "Aktualisieren", "Sicherung & Import". The running call is a floating card.
- **Behaviour rules (decided with the user, apply to both layouts):**
  - Calls are display only; there is no answer action.
  - "Anrufen" uses the existing `dial_fn` / `DialWorker` (box dial help). It is hidden for suppressed numbers.
  - Contacts are local only. Nothing writes to the Fritz!Box phonebook; deleting locally leaves the box entry alone, and the next box import may bring it back (accepted).
  - Voicemail: playing marks it read on the box (existing `voicemail_audio_fn`) and never deletes. Deleting only happens through the explicit "Löschen" button with the existing confirmation text, and calls `voicemail_delete_fn`.
- **Backup / restore (new).** Backup uses SQLite's online backup API from a background task with its **own** connection (see the threading rules) into a file I choose (default name `anrufverlauf-YYYY-MM-DD.sqlite`). Its time and row counts are recorded in `sync_state`. Restore checks the file first: it must be SQLite, have the app's tables, and have `user_version` ≤ the current schema. After a confirmation it backs up into the live database, re-runs migrations, and asks the active layout to `reload()`. No automatic or scheduled backups in this spec.
- **Unchanged pieces reused as they are:** `SyncService`, `FritzBoxClient`, `CallMonitorThread`, `IncomingCallPopup`, `ContactEditDialog`, `PhonebookPickerDialog`, phonebook file import/export, settings and credentials dialogs, shutdown failsafe.
- **Data the prototype used as its shape** (from the prototype, trimmed):

  ```text
  Entry  { id, ts, type: in|out|missed|rejected|vm, number, dur|null, seen, device, line }
  Person { key: "c<contactId>" | "n<number>", name, contact|null, items[], unseen, last }
  ```

## Testing Decisions

- **Good tests check what you can see from outside**: what the query module returns for a given database and filter, and what the window shows or does after a user action. They don't check widget internals, private attributes or layout geometry.
- **Seam 1: the history query module (no Qt).** Tested against the in-memory SQLite `connection` fixture with real migrations applied, in the style of the existing `test_db_repository.py`. Cases:
  - grouping several numbers of one local contact into one person
  - unknown numbers as their own person; all suppressed numbers as a single person
  - search by name and by number in both national and international form
  - date range limits, including entries exactly on the start and end days
  - type filter and unseen-only
  - watermark logic: global vs. per person, missed vs. received, voicemail `is_new`
  - merged ordering of calls and voicemails
  - a person drops out of `people()` when the date filter excludes all of their entries
- **Seam 2: `MainWindow` with the layout setting**, via pytest-qt in the style of `test_main_window.py` (fake `sync_fn`/`dial_fn`/voicemail functions, offscreen platform from `conftest.py`). Run the same tests for both layouts (parametrized). Cases:
  - the configured layout is built on start
  - switching layouts in settings swaps the central area and keeps search and dates
  - sync updates the views and the last-sync time
  - a live ring/connect/disconnect shows and clears the running-call display and triggers a sync
  - "Anrufen" calls `dial_fn` with the right number, and there is no button for suppressed numbers
  - opening a person clears their unseen count
  - voicemail delete calls `delete_fn` only after confirming, and playing never calls it
  - creating/editing/deleting a contact updates the history names
  - backup writes a file a restore accepts, and restore rejects a non-backup file
- Layout widgets get no separate test files; they are covered through `MainWindow`. Existing per-view tests (`test_all_calls_view.py`, `test_voicemail_view.py`, `test_phonebook_view.py`, …) stay as long as those views stay.

## Out of Scope

- Answering, rejecting or forwarding calls from the app.
- Writing contacts to the Fritz!Box phonebook, or syncing in both directions.
- Remembering deleted contacts so a box import skips them.
- Variant B ("Zeitstrahl") from the prototype.
- Automatic or scheduled backups and backup rotation.
- Seen state per single call (decided: per-person watermark).
- Transcribing voicemails.
- Changes to sync, the TR-064 client or the call-monitor protocol.

## Further Notes

- `GLOSSARY.md` only defines "Background task". This spec introduces **Person** (a local phonebook contact with all of its numbers, or a single unknown number, or the one "Unbekannt" for suppressed numbers) and **Unseen**. Record both with `/domain-modeling` when implementing.
- The earlier decision "missed-call 'new' state is one timestamp, not a per-row flag" stays; the per-person watermark extends it.
- Add CHANGELOG entries under `[Unreleased]` (English; German UI labels quoted literally, for example "Drei Spalten", "Personen", "Sicherung & Import").
- Suggested order: (1) history query module plus migration, with tests; (2) layout interface and `MainWindow` refactor with "Drei Spalten" built from the existing views, so the app keeps working; (3) "Personen" layout; (4) backup/restore; (5) settings choice and switching without restart.
