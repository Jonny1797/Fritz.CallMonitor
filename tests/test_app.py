from fritz_callhistory.app import _build_import_from_box_fn, _build_sync_fn
from fritz_callhistory.config import Config
from fritz_callhistory.db.connection import connect
from fritz_callhistory.db.repository import LocalPhonebookRepository
from fritz_callhistory.fritz.client import FritzPhonebookContact, FritzPhonebookNumber
from fritz_callhistory.gui.workers import ImportFromBoxWorker, SyncWorker


def test_build_sync_fn_runs_in_real_worker_thread_without_connection_errors(qtbot, tmp_path, mocker):
    """sync_fn läuft im SyncWorker-QThread, nicht im Test-/GUI-Thread. sqlite3-Connections
    dürfen nicht threadübergreifend verwendet werden - dieser Test reproduziert also die
    echten Thread-Grenzen, statt sync_fn direkt (im Test-Thread) aufzurufen."""
    db_path = tmp_path / "callhistory.sqlite3"
    mocker.patch("fritz_callhistory.app.database_file", return_value=db_path)
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value="secret")

    fake_client = mocker.Mock()
    fake_client.get_calls.return_value = []
    fake_client.phonebook_ids.return_value = []
    mocker.patch("fritz_callhistory.app.FritzBoxClient", return_value=fake_client)

    cfg = Config(address="192.168.178.1", username="admin")
    sync_fn = _build_sync_fn(cfg)
    assert sync_fn is not None

    worker = SyncWorker(sync_fn)
    failures = []
    worker.sync_failed.connect(failures.append)

    with qtbot.waitSignal(worker.finished_sync, timeout=3000, raising=True) as blocker:
        worker.start()

    assert failures == []
    assert blocker.args == [0, 0]


def test_build_import_from_box_fn_runs_in_real_worker_thread_and_creates_contact(
    qtbot, tmp_path, mocker
):
    db_path = tmp_path / "callhistory.sqlite3"
    mocker.patch("fritz_callhistory.app.database_file", return_value=db_path)
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value="secret")

    fake_client = mocker.Mock()
    fake_client.phonebook_ids.return_value = [0]
    fake_client.phonebook_contacts_detailed.return_value = [
        FritzPhonebookContact(
            uniqueid="7",
            name="Max Mustermann",
            category="0",
            numbers=[FritzPhonebookNumber(value="0171 2345678", type="mobile")],
        )
    ]
    mocker.patch("fritz_callhistory.app.FritzBoxClient", return_value=fake_client)

    cfg = Config(address="192.168.178.1", username="admin")
    import_fn = _build_import_from_box_fn(cfg)
    assert import_fn is not None

    worker = ImportFromBoxWorker(import_fn)
    failures = []
    worker.import_failed.connect(failures.append)

    with qtbot.waitSignal(worker.finished_import, timeout=3000, raising=True) as blocker:
        worker.start()

    assert failures == []
    assert blocker.args == [1]

    connection = connect(db_path)
    contacts = LocalPhonebookRepository(connection).list_all()
    connection.close()
    assert len(contacts) == 1
    assert contacts[0].display_name == "Max Mustermann"
    assert contacts[0].box_uniqueid == "7"


def test_build_import_from_box_fn_returns_none_without_stored_password(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value=None)
    cfg = Config(address="192.168.178.1", username="admin")

    assert _build_import_from_box_fn(cfg) is None
