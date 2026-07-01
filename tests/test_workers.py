from fritz_callhistory.fritz.exceptions import FritzBoxConnectionError
from fritz_callhistory.gui.workers import SyncWorker


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
