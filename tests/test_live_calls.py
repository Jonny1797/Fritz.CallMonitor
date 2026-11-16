from fritz_callhistory.gui.live_calls import LiveCall, LiveCallState
from fritz_callhistory.sync.caller_directory import CallerIdentity

IDENTITY = CallerIdentity("+49301234567", False, None, None, None)


def _live(state=LiveCallState.RINGING, answered=False, started_at="2026-06-10T12:00:00"):
    return LiveCall("030 1234567", "069987654", IDENTITY, started_at, state, answered)


def test_ringing_label_and_icon():
    assert _live().display() == "🔔 Klingelt …"


def test_connected_label_and_icon():
    assert _live(LiveCallState.CONNECTED, answered=True).display() == "📞 Verbunden …"


def test_ended_unanswered_shows_missed():
    assert _live(LiveCallState.ENDED).display() == "✕ Verpasst"


def test_ended_answered_shows_incoming():
    assert _live(LiveCallState.ENDED, answered=True).display() == "↘ Eingehend"


def test_new_missed_only_for_ended_unanswered_after_last_seen():
    last_seen = "2026-06-10T11:00:00"
    assert _live(LiveCallState.ENDED).is_new_missed(last_seen)
    assert not _live(LiveCallState.ENDED, answered=True).is_new_missed(last_seen)
    assert not _live(LiveCallState.RINGING).is_new_missed(last_seen)
    assert not _live(LiveCallState.CONNECTED, answered=True).is_new_missed(last_seen)
    assert not _live(LiveCallState.ENDED).is_new_missed("2026-06-10T13:00:00")
    assert not _live(LiveCallState.ENDED).is_new_missed(None)


def test_direction_sort_key_orders_connected_ringing_ended_before_box_codes():
    keys = [
        _live(state).direction_sort_key
        for state in (LiveCallState.ENDED, LiveCallState.RINGING, LiveCallState.CONNECTED)
    ]
    assert sorted(keys) == keys[::-1]
    assert all(key < (1, 1) for key in keys)


def test_shares_call_record_fields_for_date_duration_and_port_columns():
    call = _live(started_at="2026-06-10T12:00:00")
    assert (call.call_date, call.duration_seconds, call.port, call.device) == (
        "2026-06-10T12:00:00",
        None,
        None,
        None,
    )
