from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from fritz_callhistory.db.repository import VoicemailRepository
from fritz_callhistory.gui.voicemail_view import VoicemailView


def _insert_message(connection, **overrides):
    defaults = dict(
        tam_index=0,
        box_path="/download.lua?path=/data/tam/rec/rec.0.000",
        caller_number="+491712345678",
        called_number="+4969123456",
        message_date="2026-06-01T10:00:00",
        duration_seconds=4,
        raw_name="Georg",
        is_new=True,
    )
    defaults.update(overrides)
    VoicemailRepository(connection).insert_or_update(**defaults)


def _select_row(view, row: int) -> None:
    index = view._proxy.mapFromSource(view._model.index(row, 0))
    view._table.selectionModel().select(
        index,
        view._table.selectionModel().SelectionFlag.ClearAndSelect
        | view._table.selectionModel().SelectionFlag.Rows,
    )


def test_view_lists_visible_messages(qtbot, connection):
    _insert_message(connection)

    view = VoicemailView(connection)
    qtbot.addWidget(view)

    assert view._model.rowCount() == 1


def test_delete_message_removes_local_row(qtbot, connection):
    _insert_message(connection, box_path="/download.lua?path=/data/tam/rec/rec.0.000")
    _insert_message(connection, box_path="/download.lua?path=/data/tam/rec/rec.0.001")
    view = VoicemailView(connection, delete_fn=lambda message: None)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view._delete_message(message)
    qtbot.waitUntil(lambda: view._action_thread is None, timeout=2000)

    assert view._model.rowCount() == 1
    assert view._model.message_at(0).box_path != message.box_path


def test_delete_message_persists_across_reload(qtbot, connection):
    _insert_message(connection)
    view = VoicemailView(connection, delete_fn=lambda message: None)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view._delete_message(message)
    qtbot.waitUntil(lambda: view._action_thread is None, timeout=2000)
    view.reload()

    assert view._model.rowCount() == 0


def test_new_voicemail_count_reflects_unheard_messages(qtbot, connection):
    _insert_message(connection, box_path="/download.lua?path=/data/tam/rec/rec.0.000", is_new=True)
    _insert_message(connection, box_path="/download.lua?path=/data/tam/rec/rec.0.001", is_new=False)

    view = VoicemailView(connection)
    qtbot.addWidget(view)

    assert view.new_voicemail_count == 1


def test_new_voicemail_count_changed_signal_emits_on_reload(qtbot, connection):
    view = VoicemailView(connection)
    qtbot.addWidget(view)

    _insert_message(connection, is_new=True)

    with qtbot.waitSignal(view.new_voicemail_count_changed, timeout=1000) as blocker:
        view.reload()

    assert blocker.args == [1]


def test_play_message_does_nothing_without_audio_fetch_fn(qtbot, connection):
    _insert_message(connection)
    view = VoicemailView(connection, audio_fetch_fn=None)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view.play_message(message)

    assert view._audio_thread is None


def test_play_message_fetches_audio_in_background_worker(qtbot, connection):
    _insert_message(connection)
    view = VoicemailView(connection, audio_fetch_fn=lambda message: b"RIFF...")
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view.play_message(message)
    qtbot.waitUntil(lambda: view._audio_thread is None, timeout=2000)

    assert view._audio_bytes is not None
    assert view._audio_bytes.data() == b"RIFF..."


def test_hung_audio_fetch_does_not_block_gui_thread(qtbot, connection):
    """Reproduces the reported "loading a message blocks the whole app" symptom
    at the unit level: a stalled audio_fetch_fn (standing in for a hung network
    call, e.g. fritz/client.py's voicemail_audio() before its missing timeout was
    added) must not freeze the GUI event loop - only VoicemailAudioWorker itself
    should be stuck, confirmed here by a QTimer still firing while the fetch
    hangs, and by the app recovering cleanly once the fetch is unblocked."""
    import threading

    from PySide6.QtCore import QTimer

    release_event = threading.Event()

    def hanging_fetch(message):
        release_event.wait(timeout=5)
        return b"RIFF..."

    _insert_message(connection)
    view = VoicemailView(connection, audio_fetch_fn=hanging_fetch)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view.play_message(message)

    ticked = []
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: ticked.append(True))
    timer.start(50)
    qtbot.waitUntil(lambda: bool(ticked), timeout=1000)

    assert view._audio_thread is not None
    view.play_message(message)  # guarded no-op while a fetch is already in flight
    assert view._audio_thread is not None

    release_event.set()
    qtbot.waitUntil(lambda: view._audio_thread is None, timeout=2000)


def test_play_message_shows_error_on_fetch_failure(qtbot, connection):
    from fritz_callhistory.fritz.exceptions import FritzBoxConnectionError

    def failing_fetch(message):
        raise FritzBoxConnectionError("Box nicht erreichbar")

    _insert_message(connection)
    view = VoicemailView(connection, audio_fetch_fn=failing_fetch)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view.play_message(message)
    qtbot.waitUntil(lambda: view._audio_thread is None, timeout=2000)

    assert "Box nicht erreichbar" in view._now_playing_label.text()


def test_playing_a_message_clears_unread_styling_immediately(qtbot, connection):
    _insert_message(connection, is_new=True)
    view = VoicemailView(connection, audio_fetch_fn=lambda message: b"RIFF...")
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view.play_message(message)
    qtbot.waitUntil(lambda: view._audio_thread is None, timeout=2000)

    assert view._model.message_at(0).is_new is False


def test_action_buttons_disabled_without_selection(qtbot, connection):
    _insert_message(connection)
    view = VoicemailView(connection)
    qtbot.addWidget(view)

    assert view._play_button.isEnabled() is False
    assert view._call_button.isEnabled() is False
    assert view._read_button.isEnabled() is False
    assert view._delete_button.isEnabled() is False


def test_action_buttons_enabled_for_selected_unread_message_with_number(qtbot, connection):
    _insert_message(connection, caller_number="+491712345678", is_new=True)
    view = VoicemailView(connection)
    qtbot.addWidget(view)

    _select_row(view, 0)

    assert view._play_button.isEnabled() is True
    assert view._call_button.isEnabled() is True
    assert view._read_button.isEnabled() is True
    assert view._delete_button.isEnabled() is True


def test_call_button_disabled_without_caller_number(qtbot, connection):
    _insert_message(connection, caller_number=None)
    view = VoicemailView(connection)
    qtbot.addWidget(view)

    _select_row(view, 0)

    assert view._call_button.isEnabled() is False


def test_read_button_disabled_for_already_read_message(qtbot, connection):
    _insert_message(connection, is_new=False)
    view = VoicemailView(connection)
    qtbot.addWidget(view)

    _select_row(view, 0)

    assert view._read_button.isEnabled() is False


def test_mark_read_does_nothing_without_mark_read_fn(qtbot, connection):
    _insert_message(connection)
    view = VoicemailView(connection, mark_read_fn=None)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view._mark_read(message)

    assert view._action_thread is None


def test_mark_read_updates_local_state_via_background_worker(qtbot, connection):
    calls = []
    _insert_message(connection, is_new=True)
    view = VoicemailView(connection, mark_read_fn=lambda message: calls.append(message.id))
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view._mark_read(message)
    qtbot.waitUntil(lambda: view._action_thread is None, timeout=2000)

    assert calls == [message.id]
    assert view._model.message_at(0).is_new is False


def test_action_buttons_disabled_while_action_in_flight(qtbot, connection):
    """A running Gelesen/Löschen action must disable all four buttons - otherwise
    a second action (e.g. confirming a delete) could be triggered while the first
    is still in flight and silently no-op via the shared _action_thread guard."""
    import threading

    release_event = threading.Event()

    def hanging_mark_read(message):
        release_event.wait(timeout=5)

    _insert_message(connection, is_new=True)
    view = VoicemailView(connection, mark_read_fn=hanging_mark_read)
    qtbot.addWidget(view)
    _select_row(view, 0)
    assert view._read_button.isEnabled() is True

    view._on_read_button_clicked()

    assert view._action_thread is not None
    assert view._play_button.isEnabled() is False
    assert view._call_button.isEnabled() is False
    assert view._read_button.isEnabled() is False
    assert view._delete_button.isEnabled() is False

    release_event.set()
    qtbot.waitUntil(lambda: view._action_thread is None, timeout=2000)


def test_delete_does_nothing_without_delete_fn(qtbot, connection):
    _insert_message(connection)
    view = VoicemailView(connection, delete_fn=None)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view._delete_message(message)

    assert view._action_thread is None


def test_action_worker_shows_error_on_failure(qtbot, connection):
    from fritz_callhistory.fritz.exceptions import FritzBoxConnectionError

    def failing_delete(message):
        raise FritzBoxConnectionError("Box nicht erreichbar")

    _insert_message(connection)
    view = VoicemailView(connection, delete_fn=failing_delete)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view._delete_message(message)
    qtbot.waitUntil(lambda: view._action_thread is None, timeout=2000)

    assert "Box nicht erreichbar" in view._now_playing_label.text()
    # a failed box call must not remove the local row
    assert view._model.rowCount() == 1


def test_focus_search_is_a_noop(qtbot, connection):
    view = VoicemailView(connection)
    qtbot.addWidget(view)

    view.focus_search()  # kein Suchfeld in diesem Tab - darf nicht crashen


def test_dial_selected_emits_call_requested_for_selected_message(qtbot, connection):
    _insert_message(connection, caller_number="+491712345678")
    view = VoicemailView(connection)
    qtbot.addWidget(view)
    _select_row(view, 0)

    with qtbot.waitSignal(view.call_requested, timeout=1000) as blocker:
        view.dial_selected()

    assert blocker.args == ["+491712345678"]


def test_dial_selected_does_nothing_without_selection(qtbot, connection):
    _insert_message(connection, caller_number="+491712345678")
    view = VoicemailView(connection)
    qtbot.addWidget(view)
    signal_spy = []
    view.call_requested.connect(signal_spy.append)

    view.dial_selected()

    assert signal_spy == []


def test_delete_button_click_asks_for_confirmation_before_deleting(qtbot, connection, mocker):
    mocker.patch(
        "fritz_callhistory.gui.voicemail_view.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    )
    calls = []
    _insert_message(connection)
    view = VoicemailView(connection, delete_fn=lambda message: calls.append(message.id))
    qtbot.addWidget(view)
    _select_row(view, 0)

    view._on_delete_button_clicked()

    assert calls == []
    assert view._action_thread is None


def test_seek_slider_click_jumps_to_clicked_position(qtbot):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from fritz_callhistory.gui.voicemail_view import _SeekSlider

    slider = _SeekSlider(Qt.Orientation.Horizontal)
    qtbot.addWidget(slider)
    slider.resize(200, 20)
    slider.setRange(0, 1000)

    moved = []
    slider.sliderMoved.connect(moved.append)

    click_pos = QPoint(150, 10)  # ~75% along the width
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        click_pos,
        slider.mapToGlobal(click_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    slider.mousePressEvent(event)
    QApplication.processEvents()

    assert moved
    assert slider.value() == moved[-1]
    assert moved[-1] > 500  # clicked past the midpoint
