# Fritz!Box Anrufhistorie

Desktop-App, die die Anrufliste einer Fritz!Box lokal spiegelt und als durchsuchbare Anrufliste, Telefonbuch und Anrufbeantworter anzeigt.

## Language

**Background task**:
A single blocking job (usually one request to the Fritz!Box) that runs without freezing the window; at most one task of each kind runs at a time, and quitting waits for running tasks to finish.
_Avoid_: worker, thread, job
