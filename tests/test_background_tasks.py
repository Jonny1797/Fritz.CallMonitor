import threading

import pytest
from PySide6.QtCore import QObject

from fritz_callhistory.fritz.exceptions import FritzBoxAuthError, FritzBoxError
from fritz_callhistory.gui.background_tasks import BackgroundTasks


@pytest.fixture
def tasks(qtbot):
    t = BackgroundTasks()
    yield t
    # Test-Aufräumen: nichts Laufendes zurücklassen
    qtbot.waitUntil(t.is_idle, timeout=3000)


class Recorder:
    def __init__(self):
        self.successes = []
        self.errors = []

    def ok(self, value):
        self.successes.append(value)

    def err(self, exc):
        self.errors.append(exc)


def test_success_passes_value(qtbot, tasks):
    ctx, rec = QObject(), Recorder()
    assert tasks.start(lambda: 42, ctx, rec.ok, rec.err)
    qtbot.waitUntil(lambda: rec.successes == [42], timeout=3000)
    assert rec.errors == []


def test_success_without_value_passes_none(qtbot, tasks):
    ctx, rec = QObject(), Recorder()
    tasks.start(lambda: None, ctx, rec.ok, rec.err)
    qtbot.waitUntil(lambda: rec.successes == [None], timeout=3000)


def test_fritzbox_error_reaches_on_error_unchanged(qtbot, tasks):
    ctx, rec = QObject(), Recorder()
    original = FritzBoxAuthError("falsches Passwort")

    def fn():
        raise original

    tasks.start(fn, ctx, rec.ok, rec.err)
    qtbot.waitUntil(lambda: len(rec.errors) == 1, timeout=3000)
    assert rec.errors[0] is original
    assert rec.successes == []


def test_unexpected_exception_is_wrapped(qtbot, tasks):
    ctx, rec = QObject(), Recorder()

    def fn():
        raise ValueError("kaputt")

    tasks.start(fn, ctx, rec.ok, rec.err)
    qtbot.waitUntil(lambda: len(rec.errors) == 1, timeout=3000)
    assert type(rec.errors[0]) is FritzBoxError
    assert str(rec.errors[0]) == "Unerwarteter Fehler: kaputt"


def test_same_key_refused_while_running_allowed_after(qtbot, tasks):
    ctx, rec = QObject(), Recorder()
    release = threading.Event()
    assert tasks.start(release.wait, ctx, rec.ok, rec.err, key="sync")
    assert tasks.is_running("sync")
    assert tasks.start(lambda: "refused", ctx, rec.ok, rec.err, key="sync") is False
    release.set()
    qtbot.waitUntil(lambda: not tasks.is_running("sync"), timeout=3000)
    assert tasks.start(lambda: 2, ctx, rec.ok, rec.err, key="sync")
    qtbot.waitUntil(lambda: 2 in rec.successes, timeout=3000)
    assert "refused" not in rec.successes


def test_different_keys_and_no_key_run_concurrently(qtbot, tasks):
    ctx, rec = QObject(), Recorder()
    release = threading.Event()
    assert tasks.start(release.wait, ctx, rec.ok, rec.err, key="a")
    assert tasks.start(release.wait, ctx, rec.ok, rec.err, key="b")
    assert tasks.start(release.wait, ctx, rec.ok, rec.err)
    assert tasks.start(release.wait, ctx, rec.ok, rec.err)  # ohne Schlüssel nie abgelehnt
    assert tasks.is_running("a") and tasks.is_running("b")
    release.set()
    qtbot.waitUntil(lambda: len(rec.successes) == 4, timeout=3000)


def test_is_running_false_inside_callbacks(qtbot, tasks):
    ctx = QObject()
    seen = []

    tasks.start(lambda: 1, ctx, lambda _: seen.append(tasks.is_running("k")), print, key="k")

    def boom():
        raise FritzBoxError("x")

    tasks.start(boom, ctx, print, lambda _: seen.append(tasks.is_running("e")), key="e")
    qtbot.waitUntil(lambda: len(seen) == 2, timeout=3000)
    assert seen == [False, False]


def test_callbacks_skipped_after_context_destroyed(qtbot, tasks):
    ctx, rec = QObject(), Recorder()
    release = threading.Event()
    tasks.start(release.wait, ctx, rec.ok, rec.err, key="k")
    ctx.deleteLater()
    qtbot.wait(50)
    release.set()
    qtbot.waitUntil(lambda: not tasks.is_running("k"), timeout=3000)
    qtbot.wait(50)
    assert rec.successes == [] and rec.errors == []


def test_starts_refused_and_callbacks_skipped_after_quit_begins(qtbot, tasks):
    ctx, rec = QObject(), Recorder()
    release = threading.Event()
    ran = []
    tasks.start(lambda: ran.append("work") or release.wait(), ctx, rec.ok, rec.err, key="k")
    qtbot.waitUntil(lambda: ran == ["work"], timeout=3000)
    assert tasks.is_quitting is False
    tasks.begin_quit()
    assert tasks.is_quitting is True
    assert tasks.start(lambda: 1, ctx, rec.ok, rec.err, key="other") is False
    with qtbot.waitSignal(tasks.all_finished, timeout=3000):
        release.set()
    assert rec.successes == [] and rec.errors == []


def test_all_finished_emitted_when_last_task_ends(qtbot, tasks):
    ctx, rec = QObject(), Recorder()
    first, second = threading.Event(), threading.Event()
    tasks.start(first.wait, ctx, rec.ok, rec.err)
    tasks.start(second.wait, ctx, rec.ok, rec.err)
    emitted = []
    tasks.all_finished.connect(lambda: emitted.append(1))
    first.set()
    qtbot.waitUntil(lambda: len(rec.successes) == 1, timeout=3000)
    assert emitted == []
    with qtbot.waitSignal(tasks.all_finished, timeout=3000):
        second.set()


def test_exit_fn_called_when_tasks_outlive_timeout(qtbot):
    calls = []
    t = BackgroundTasks(exit_fn=lambda: calls.append(1), failsafe_timeout_s=0.05)
    release = threading.Event()
    t.start(release.wait, QObject(), print, print)
    t.begin_quit()
    qtbot.waitUntil(lambda: calls == [1], timeout=3000)
    release.set()
    qtbot.waitUntil(t.is_idle, timeout=3000)


def test_exit_fn_not_called_when_tasks_end_in_time(qtbot):
    calls = []
    t = BackgroundTasks(exit_fn=lambda: calls.append(1), failsafe_timeout_s=0.2)
    release = threading.Event()
    t.start(release.wait, QObject(), print, print)
    t.begin_quit()
    with qtbot.waitSignal(t.all_finished, timeout=3000):
        release.set()
    qtbot.wait(400)
    assert calls == []
