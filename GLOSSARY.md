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

**Box Telefonbuch**:
The read-only copy of the Fritz!Box's phonebooks, refreshed on every sync.
_Avoid_: Box phonebook cache, Box contacts

**Caller directory**:
The one place that answers "who is behind this number?" for a Caller.
_Avoid_: name resolver, lookup

**Box gateway**:
The app's one way to act on the Fritz!Box with the stored login: sync, dial, Box Telefonbuch import, Anrufbeantworter actions, credentials check.
_Avoid_: Box session, client, closure
