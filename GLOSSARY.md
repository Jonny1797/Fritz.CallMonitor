# Fritz!Box Anrufhistorie

Desktop-App, die die Anrufliste einer Fritz!Box lokal spiegelt und als durchsuchbare Anrufliste, Telefonbuch und Anrufbeantworter anzeigt.

## Language

**Background task**:
A single blocking job (usually one request to the Fritz!Box) that runs without freezing the window; at most one task of each kind runs at a time, and quitting waits for running tasks to finish.
_Avoid_: worker, thread, job

**Caller**:
A phone number from the call history, together with the identity resolved for it (name, notes, anonymous or not).
_Avoid_: contact (for this meaning)

**Telefonbuch contact**:
An entry the user maintains in the local Telefonbuch, with a name, notes and one or more numbers.
_Avoid_: local contact, phonebook entry

**Default number**:
The number of a Telefonbuch contact the user marked as preferred; a contact has at most one, and may have none.
_Avoid_: primary number, main number

**Import duplicate**:
A contact in an imported file whose numbers are exactly the numbers of one existing Telefonbuch contact; it is skipped, not imported again.
_Avoid_: duplicate contact, match

**Adopt**:
During a Box Telefonbuch import, linking a Box contact to an existing Telefonbuch contact that has no Box link yet and exactly the same numbers, instead of creating a second contact.
_Avoid_: merge, match, link up

**Box Telefonbuch**:
The read-only copy of the Fritz!Box's phonebooks, refreshed on every sync.
_Avoid_: Box phonebook cache, Box contacts

**Caller directory**:
The one place that answers "who is behind this number?" for a Caller.
_Avoid_: name resolver, lookup

**Box gateway**:
The app's one way to act on the Fritz!Box with the stored login: sync, dial, Box Telefonbuch import, Anrufbeantworter actions, credentials check.
_Avoid_: Box session, client, closure

**Call type**:
What happened on a call, as the Fritz!Box reports it: Eingehend, Verpasst, Ausgehend, Abgelehnt, or an active variant of incoming/outgoing.
_Avoid_: call kind, direction (direction is only one aspect of it)

**Missed call**:
An incoming call nobody answered (Verpasst). A rejected call (Abgelehnt) is not a missed call.
_Avoid_: unanswered call

**Counterparty number**:
The other side's number on a call: the called number for outgoing calls, the caller's number otherwise.
_Avoid_: remote number, call number

**Live call**:
An incoming call seen by the call monitor that the call history doesn't contain yet. It is Klingelt, then Verbunden once answered; after it ends it shows as Verpasst (never answered) or Eingehend (answered) until the next sync brings the real entry.
_Avoid_: active call, pending call

**Release**:
A published, tagged version of the app, with its download files and release notes.
_Avoid_: build, version (for this meaning)

**App update**:
Replacing the running app with a newer Release, started by the user from the menu.
_Avoid_: upgrade, patch
