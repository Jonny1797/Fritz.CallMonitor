from fritz_callhistory.fritz.exceptions import FritzBoxConnectionError
from fritz_callhistory.gui.workers import (
    DialWorker,
    ImportFromBoxWorker,
    SyncWorker,
    VoicemailActionWorker,
    VoicemailAudioWorker,
)


def test_sync_worker_emits_finished_signal_with_result(qtbot):
    worker = SyncWorker(lambda: (3, 2))

    with qtbot.waitSignal(worker.finished_sync, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == [3, 2]


def test_sync_worker_emits_failed_signal_on_fritzbox_error(qtbot):
    def sync_fn():
        raise FritzBoxConnectionError("Box nicht erreichbar")

    worker = SyncWorker(sync_fn)

    with qtbot.waitSignal(worker.sync_failed, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["Box nicht erreichbar"]


def test_sync_worker_emits_failed_signal_on_unexpected_error(qtbot):
    def sync_fn():
        raise ValueError("boom")

    worker = SyncWorker(sync_fn)

    with qtbot.waitSignal(worker.sync_failed, timeout=2000) as blocker:
        worker.start()

    assert "boom" in blocker.args[0]


def test_import_from_box_worker_emits_finished_signal_with_result(qtbot):
    worker = ImportFromBoxWorker(lambda: 5)

    with qtbot.waitSignal(worker.finished_import, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == [5]


def test_import_from_box_worker_emits_failed_signal_on_fritzbox_error(qtbot):
    def import_fn():
        raise FritzBoxConnectionError("Box nicht erreichbar")

    worker = ImportFromBoxWorker(import_fn)

    with qtbot.waitSignal(worker.import_failed, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["Box nicht erreichbar"]


def test_import_from_box_worker_emits_failed_signal_on_unexpected_error(qtbot):
    def import_fn():
        raise ValueError("boom")

    worker = ImportFromBoxWorker(import_fn)

    with qtbot.waitSignal(worker.import_failed, timeout=2000) as blocker:
        worker.start()

    assert "boom" in blocker.args[0]


def test_dial_worker_emits_succeeded_signal(qtbot):
    calls = []
    worker = DialWorker(lambda: calls.append("+491234567"))

    with qtbot.waitSignal(worker.dial_succeeded, timeout=2000):
        worker.start()

    assert calls == ["+491234567"]


def test_dial_worker_emits_failed_signal_on_fritzbox_error(qtbot):
    def dial_fn():
        raise FritzBoxConnectionError("Box nicht erreichbar")

    worker = DialWorker(dial_fn)

    with qtbot.waitSignal(worker.dial_failed, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["Box nicht erreichbar"]


def test_dial_worker_emits_failed_signal_on_unexpected_error(qtbot):
    def dial_fn():
        raise ValueError("boom")

    worker = DialWorker(dial_fn)

    with qtbot.waitSignal(worker.dial_failed, timeout=2000) as blocker:
        worker.start()

    assert "boom" in blocker.args[0]


def test_voicemail_audio_worker_emits_ready_signal_with_bytes(qtbot):
    worker = VoicemailAudioWorker(lambda: b"RIFF...")

    with qtbot.waitSignal(worker.audio_ready, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == [b"RIFF..."]


def test_voicemail_audio_worker_emits_failed_signal_on_fritzbox_error(qtbot):
    def audio_fn():
        raise FritzBoxConnectionError("Box nicht erreichbar")

    worker = VoicemailAudioWorker(audio_fn)

    with qtbot.waitSignal(worker.audio_failed, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["Box nicht erreichbar"]


def test_voicemail_audio_worker_emits_failed_signal_on_unexpected_error(qtbot):
    def audio_fn():
        raise ValueError("boom")

    worker = VoicemailAudioWorker(audio_fn)

    with qtbot.waitSignal(worker.audio_failed, timeout=2000) as blocker:
        worker.start()

    assert "boom" in blocker.args[0]


def test_voicemail_action_worker_emits_succeeded_signal(qtbot):
    calls = []
    worker = VoicemailActionWorker(lambda: calls.append("done"))

    with qtbot.waitSignal(worker.action_succeeded, timeout=2000):
        worker.start()

    assert calls == ["done"]


def test_voicemail_action_worker_emits_failed_signal_on_fritzbox_error(qtbot):
    def action_fn():
        raise FritzBoxConnectionError("Box nicht erreichbar")

    worker = VoicemailActionWorker(action_fn)

    with qtbot.waitSignal(worker.action_failed, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["Box nicht erreichbar"]


def test_voicemail_action_worker_emits_failed_signal_on_unexpected_error(qtbot):
    def action_fn():
        raise ValueError("boom")

    worker = VoicemailActionWorker(action_fn)

    with qtbot.waitSignal(worker.action_failed, timeout=2000) as blocker:
        worker.start()

    assert "boom" in blocker.args[0]
