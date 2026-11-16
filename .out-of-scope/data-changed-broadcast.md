# Data-changed broadcast instead of MainWindow wiring

The app does not have a central "data changed" notification (sync completed, Telefonbuch changed)
that views subscribe to. `MainWindow` keeps telling the views directly what to reload.

## Why this is out of scope

The request was to stop `MainWindow` from knowing each view's refresh steps. Today that knowledge
amounts to a handful of lines:

```python
# gui/main_window.py
self._phonebook_tab.contacts_changed.connect(self._calls_tab.reload_contacts)

def _on_sync_finished(self, inserted: int, updated: int) -> None:
    ...
    self._calls_tab.reload_contacts()
    self._calls_tab.clear_ended_live_calls()
    self._calls_tab.reload()
    self._voicemail_view.reload()
```

A broadcast fails the deletion test, the same test that keeps `CallsTab` passing the live-call
methods through: it moves this wiring instead of removing it. `MainWindow` builds every view, so
adding a view means editing `MainWindow` either way. Today that edit is a reload call. With the
broadcast it would be a subscription. The project would gain a new notification object (one signal
with a reason, or one signal per data source, plus a decision about where it lives) and save about
five lines across two consumers.

Direct calls also keep the order visible in one place: live calls are cleared before the calls
list is reloaded. Subscribers that each decide for themselves would hide that ordering.

Reconsider this if the number of views or data sources that react to a sync grows enough for the
wiring in `MainWindow` to stop being a short, readable list.

## Prior requests

- #8: "Architecture: broadcast \"data changed\" instead of MainWindow deciding what refreshes"
