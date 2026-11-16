from fritz_callhistory.fritz.call_types import (
    CallType,
    counterparty_number,
    display,
    icon,
    is_missed,
    is_outgoing,
    label,
)


def test_missed_only_for_code_2():
    assert is_missed(2)
    assert not is_missed(10)
    assert not is_missed(1)


def test_outgoing_for_3_and_11():
    assert is_outgoing(3) and is_outgoing(11)
    assert not is_outgoing(1) and not is_outgoing(9) and not is_outgoing(2)


def test_counterparty_number_per_direction():
    assert counterparty_number(3, "A", "B") == "B"
    assert counterparty_number(11, "A", "B") == "B"
    assert counterparty_number(1, "A", "B") == "A"
    assert counterparty_number(2, "A", "B") == "A"


def test_label_and_icon_per_known_code():
    expected = {
        1: ("↘", "Eingehend"),
        2: ("✕", "Verpasst"),
        3: ("↗", "Ausgehend"),
        9: ("↘", "Eingehend (aktiv)"),
        10: ("⊘", "Abgelehnt"),
        11: ("↗", "Ausgehend (aktiv)"),
        -1: ("🔔", "Klingelt …"),
        -2: ("📞", "Verbunden …"),
    }
    for code, (symbol, text) in expected.items():
        assert icon(code) == symbol
        assert label(code) == text
        assert display(code) == f"{symbol} {text}"


def test_live_states_have_documented_values():
    assert CallType.LIVE_RINGING == -1
    assert CallType.LIVE_CONNECTED == -2


def test_unknown_code_falls_back_to_bare_number():
    assert display(42) == "42"
    assert icon(42) == ""
    assert not is_missed(42) and not is_outgoing(42)
