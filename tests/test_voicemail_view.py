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


def test_view_lists_visible_messages(qtbot, connection):
    _insert_message(connection)

    view = VoicemailView(connection)
    qtbot.addWidget(view)

    assert view._model.rowCount() == 1


def test_view_excludes_hidden_messages(qtbot, connection):
    _insert_message(connection, box_path="/download.lua?path=/data/tam/rec/rec.0.000")
    _insert_message(connection, box_path="/download.lua?path=/data/tam/rec/rec.0.001")
    view = VoicemailView(connection)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view._hide_message(message)

    assert view._model.rowCount() == 1
    assert view._model.message_at(0).box_path != message.box_path


def test_hide_message_persists_across_reload(qtbot, connection):
    _insert_message(connection)
    view = VoicemailView(connection)
    qtbot.addWidget(view)
    message = view._model.message_at(0)

    view._hide_message(message)
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
