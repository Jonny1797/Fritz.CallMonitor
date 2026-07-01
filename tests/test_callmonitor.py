from fritz_callhistory.fritz.callmonitor import parse_ring_event


def test_parse_ring_event_valid_line():
    event = parse_ring_event("01.01.26 20:00:00;RING;0;030123456;069987654;SIP0;")

    assert event is not None
    assert event.caller_number == "030123456"
    assert event.called_number == "069987654"
    assert event.device == "SIP0"


def test_parse_ring_event_ignores_other_event_types():
    assert parse_ring_event("01.01.26 20:00:05;CALL;0;1;069987654;030123456;SIP0;") is None
    assert parse_ring_event("01.01.26 20:00:10;CONNECT;0;1;030123456;SIP0;") is None
    assert parse_ring_event("01.01.26 20:00:15;DISCONNECT;0;30;") is None


def test_parse_ring_event_ignores_malformed_lines():
    assert parse_ring_event("garbage") is None
    assert parse_ring_event("") is None
    assert parse_ring_event(";;;") is None
