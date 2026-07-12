from fritz_callhistory.fritz.exceptions import (
    FritzBoxAuthError,
    FritzBoxConnectionError,
    FritzBoxPermissionError,
)
from fritz_callhistory.gui.workers import (
    CredentialsTestWorker,
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


def test_sync_worker_emits_auth_failed_signal_on_auth_error(qtbot):
    def sync_fn():
        raise FritzBoxAuthError("401 Unauthorized")

    worker = SyncWorker(sync_fn)
    generic_failures = []
    worker.sync_failed.connect(generic_failures.append)

    with qtbot.waitSignal(worker.auth_failed, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["401 Unauthorized"]
    assert generic_failures == []  # nicht auch noch das generische Signal


def test_sync_worker_emits_failed_signal_on_unexpected_error(qtbot):
    def sync_fn():
        raise ValueError("boom")

    worker = SyncWorker(sync_fn)

    with qtbot.waitSignal(worker.sync_failed, timeout=2000) as blocker:
        worker.start()

    assert "boom" in blocker.args[0]


def test_import_from_box_worker_emits_finished_signal_with_result(qtbot):
    worker = ImportFromBoxWorker(lambda phonebook_ids: 5, [0])

    with qtbot.waitSignal(worker.finished_import, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == [5]


def test_import_from_box_worker_passes_phonebook_ids_to_import_fn(qtbot):
    captured = {}

    def import_fn(phonebook_ids):
        captured["ids"] = phonebook_ids
        return 0

    worker = ImportFromBoxWorker(import_fn, [0, 2])

    with qtbot.waitSignal(worker.finished_import, timeout=2000):
        worker.start()

    assert captured["ids"] == [0, 2]


def test_import_from_box_worker_emits_failed_signal_on_fritzbox_error(qtbot):
    def import_fn(phonebook_ids):
        raise FritzBoxConnectionError("Box nicht erreichbar")

    worker = ImportFromBoxWorker(import_fn, [0])

    with qtbot.waitSignal(worker.import_failed, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["Box nicht erreichbar"]


def test_import_from_box_worker_emits_failed_signal_on_unexpected_error(qtbot):
    def import_fn(phonebook_ids):
        raise ValueError("boom")

    worker = ImportFromBoxWorker(import_fn, [0])

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


def test_credentials_test_worker_emits_succeeded_signal(qtbot):
    worker = CredentialsTestWorker(lambda: None)

    with qtbot.waitSignal(worker.test_succeeded, timeout=2000):
        worker.start()


def test_credentials_test_worker_emits_auth_failed_signal_on_auth_error(qtbot):
    def test_fn():
        raise FritzBoxAuthError("401 Unauthorized")

    worker = CredentialsTestWorker(test_fn)
    other_signals = []
    worker.connection_failed.connect(other_signals.append)
    worker.permission_denied.connect(other_signals.append)

    with qtbot.waitSignal(worker.auth_failed, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["401 Unauthorized"]
    assert other_signals == []


def test_credentials_test_worker_emits_permission_denied_signal_on_permission_error(qtbot):
    def test_fn():
        raise FritzBoxPermissionError("fehlendes Recht")

    worker = CredentialsTestWorker(test_fn)

    with qtbot.waitSignal(worker.permission_denied, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["fehlendes Recht"]


def test_credentials_test_worker_emits_connection_failed_signal_on_connection_error(qtbot):
    def test_fn():
        raise FritzBoxConnectionError("Box nicht erreichbar")

    worker = CredentialsTestWorker(test_fn)

    with qtbot.waitSignal(worker.connection_failed, timeout=2000) as blocker:
        worker.start()

    assert blocker.args == ["Box nicht erreichbar"]


def test_credentials_test_worker_emits_connection_failed_signal_on_unexpected_error(qtbot):
    def test_fn():
        raise ValueError("boom")

    worker = CredentialsTestWorker(test_fn)

    with qtbot.waitSignal(worker.connection_failed, timeout=2000) as blocker:
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
