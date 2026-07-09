from fritz_callhistory.app import (
    _build_import_from_box_fn,
    _build_sync_fn,
    _build_voicemail_audio_fn,
    _build_voicemail_delete_fn,
    _build_voicemail_mark_read_fn,
    _handle_sigint,
)
from fritz_callhistory.config import Config
from fritz_callhistory.db.connection import connect
from fritz_callhistory.db.repository import LocalPhonebookRepository, VoicemailMessageRecord
from fritz_callhistory.fritz.client import (
    FritzPhonebookContact,
    FritzPhonebookNumber,
    VoicemailMessage,
)
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
    fake_client.voicemail_tam_indices.return_value = []
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


def test_build_import_from_box_fn_preserves_default_number_across_reimport(
    qtbot, tmp_path, mocker
):
    # Regression test: die Box kennt kein "Standardnummer"-Konzept, und
    # LocalPhonebookRepository.update() ersetzt bei jedem Re-Import alle
    # Nummern-Zeilen komplett - ohne explizites Matching per number_normalized
    # wuerde eine zuvor lokal gesetzte Standardnummer beim naechsten
    # "Von Box importieren" stillschweigend verloren gehen (siehe app.py's
    # _build_import_from_box_fn).
    db_path = tmp_path / "callhistory.sqlite3"
    mocker.patch("fritz_callhistory.app.database_file", return_value=db_path)
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value="secret")

    connection = connect(db_path)
    local_repo = LocalPhonebookRepository(connection)
    contact_id = local_repo.create(
        display_name="Max Mustermann",
        notes=None,
        numbers=[
            ("0171 2345678", "+491712345678", "mobile", False),
            ("030 1234567", "+49301234567", "home", True),
        ],
        box_uniqueid="7",
    )
    connection.close()

    fake_client = mocker.Mock()
    fake_client.phonebook_ids.return_value = [0]
    fake_client.phonebook_contacts_detailed.return_value = [
        FritzPhonebookContact(
            uniqueid="7",
            name="Max Mustermann",
            category="0",
            numbers=[
                FritzPhonebookNumber(value="0171 2345678", type="mobile"),
                FritzPhonebookNumber(value="030 1234567", type="home"),
            ],
        )
    ]
    mocker.patch("fritz_callhistory.app.FritzBoxClient", return_value=fake_client)

    cfg = Config(address="192.168.178.1", username="admin")
    import_fn = _build_import_from_box_fn(cfg)
    assert import_fn is not None

    worker = ImportFromBoxWorker(import_fn)
    failures = []
    worker.import_failed.connect(failures.append)

    with qtbot.waitSignal(worker.finished_import, timeout=3000, raising=True):
        worker.start()

    assert failures == []

    connection = connect(db_path)
    contact = LocalPhonebookRepository(connection).get(contact_id)
    connection.close()
    assert {n.number_normalized: n.is_default for n in contact.numbers} == {
        "+491712345678": False,
        "+49301234567": True,
    }


def test_build_import_from_box_fn_returns_none_without_stored_password(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value=None)
    cfg = Config(address="192.168.178.1", username="admin")

    assert _build_import_from_box_fn(cfg) is None


def test_build_voicemail_audio_fn_returns_none_without_stored_password(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value=None)
    cfg = Config(address="192.168.178.1", username="admin")

    assert _build_voicemail_audio_fn(cfg) is None


def test_build_voicemail_audio_fn_fetches_audio_and_marks_read(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value="secret")

    fake_client = mocker.Mock()
    fake_client.voicemail_audio.return_value = b"RIFF..."
    matching_message = VoicemailMessage(
        tam_index=0,
        box_index=3,
        caller_number="0171 2345678",
        called_number="06898123456",
        date="2026-06-01T10:00:00",
        duration_seconds=4,
        name=None,
        path="/download.lua?path=/data/tam/rec/rec.0.003",
        is_new=True,
    )
    fake_client.voicemail_messages.return_value = [matching_message]
    mocker.patch("fritz_callhistory.app.FritzBoxClient", return_value=fake_client)

    cfg = Config(address="192.168.178.1", username="admin")
    audio_fn = _build_voicemail_audio_fn(cfg)
    assert audio_fn is not None

    record = VoicemailMessageRecord(
        id=1,
        tam_index=0,
        box_path="/download.lua?path=/data/tam/rec/rec.0.003",
        caller_number="0171 2345678",
        called_number="06898123456",
        message_date="2026-06-01T10:00:00",
        duration_seconds=4,
        raw_name=None,
        is_new=True,
    )

    audio = audio_fn(record)

    assert audio == b"RIFF..."
    fake_client.voicemail_audio.assert_called_once_with(record.box_path)
    fake_client.voicemail_mark_read.assert_called_once_with(0, 3)


def _matching_voicemail_message() -> VoicemailMessage:
    return VoicemailMessage(
        tam_index=0,
        box_index=3,
        caller_number="0171 2345678",
        called_number="06898123456",
        date="2026-06-01T10:00:00",
        duration_seconds=4,
        name=None,
        path="/download.lua?path=/data/tam/rec/rec.0.003",
        is_new=True,
    )


def _voicemail_record() -> VoicemailMessageRecord:
    return VoicemailMessageRecord(
        id=1,
        tam_index=0,
        box_path="/download.lua?path=/data/tam/rec/rec.0.003",
        caller_number="0171 2345678",
        called_number="06898123456",
        message_date="2026-06-01T10:00:00",
        duration_seconds=4,
        raw_name=None,
        is_new=True,
    )


def test_build_voicemail_mark_read_fn_returns_none_without_stored_password(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value=None)
    cfg = Config(address="192.168.178.1", username="admin")

    assert _build_voicemail_mark_read_fn(cfg) is None


def test_build_voicemail_mark_read_fn_resolves_box_index_and_marks_read(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value="secret")
    fake_client = mocker.Mock()
    fake_client.voicemail_messages.return_value = [_matching_voicemail_message()]
    mocker.patch("fritz_callhistory.app.FritzBoxClient", return_value=fake_client)

    cfg = Config(address="192.168.178.1", username="admin")
    mark_read_fn = _build_voicemail_mark_read_fn(cfg)
    assert mark_read_fn is not None

    mark_read_fn(_voicemail_record())

    fake_client.voicemail_mark_read.assert_called_once_with(0, 3)


def test_build_voicemail_mark_read_fn_does_nothing_when_message_gone_from_box(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value="secret")
    fake_client = mocker.Mock()
    fake_client.voicemail_messages.return_value = []
    mocker.patch("fritz_callhistory.app.FritzBoxClient", return_value=fake_client)

    cfg = Config(address="192.168.178.1", username="admin")
    mark_read_fn = _build_voicemail_mark_read_fn(cfg)
    assert mark_read_fn is not None

    mark_read_fn(_voicemail_record())

    fake_client.voicemail_mark_read.assert_not_called()


def test_build_voicemail_delete_fn_returns_none_without_stored_password(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value=None)
    cfg = Config(address="192.168.178.1", username="admin")

    assert _build_voicemail_delete_fn(cfg) is None


def test_build_voicemail_delete_fn_resolves_box_index_and_deletes(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value="secret")
    fake_client = mocker.Mock()
    fake_client.voicemail_messages.return_value = [_matching_voicemail_message()]
    mocker.patch("fritz_callhistory.app.FritzBoxClient", return_value=fake_client)

    cfg = Config(address="192.168.178.1", username="admin")
    delete_fn = _build_voicemail_delete_fn(cfg)
    assert delete_fn is not None

    delete_fn(_voicemail_record())

    fake_client.voicemail_delete.assert_called_once_with(0, 3)


def test_build_voicemail_delete_fn_does_nothing_when_message_gone_from_box(mocker):
    mocker.patch("fritz_callhistory.app.credentials.get_password", return_value="secret")
    fake_client = mocker.Mock()
    fake_client.voicemail_messages.return_value = []
    mocker.patch("fritz_callhistory.app.FritzBoxClient", return_value=fake_client)

    cfg = Config(address="192.168.178.1", username="admin")
    delete_fn = _build_voicemail_delete_fn(cfg)
    assert delete_fn is not None

    delete_fn(_voicemail_record())

    fake_client.voicemail_delete.assert_not_called()


def test_sigint_handler_forces_immediate_exit_unconditionally(mocker):
    # Regression test: SIGINT used to route through window.close(), which
    # MainWindow.closeEvent() can defer indefinitely while a worker thread is
    # busy (correct for a normal window close, but not what Ctrl+C in a
    # terminal is expected to do). The handler must force an immediate exit
    # instead, with no dependency on any window/thread state.
    force_exit = mocker.patch("fritz_callhistory.app.os._exit")

    _handle_sigint()

    force_exit.assert_called_once_with(130)
