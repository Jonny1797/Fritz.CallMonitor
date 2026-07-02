from fritz_callhistory.fritz.callmonitor import ConnectEvent, DisconnectEvent, RingEvent, parse_event


def test_parse_ring_event_valid_line():
    event = parse_event("01.01.26 20:00:00;RING;0;030123456;069987654;SIP0;")

    assert isinstance(event, RingEvent)
    assert event.connection_id == "0"
    assert event.caller_number == "030123456"
    assert event.called_number == "069987654"
    assert event.device == "SIP0"


def test_parse_connect_event_valid_line():
    event = parse_event("28.11.20 15:17:47;CONNECT;2;4;030123456;")

    assert isinstance(event, ConnectEvent)
    assert event.connection_id == "2"


def test_parse_disconnect_event_valid_line():
    event = parse_event("28.11.20 15:17:50;DISCONNECT;2;4;")

    assert isinstance(event, DisconnectEvent)
    assert event.connection_id == "2"


def test_parse_event_ignores_call_type():
    assert parse_event("01.01.26 20:00:05;CALL;0;1;069987654;030123456;SIP0;") is None


def test_parse_event_ignores_malformed_lines():
    assert parse_event("garbage") is None
    assert parse_event("") is None
    assert parse_event(";;;") is None


def test_parse_event_ignores_incomplete_ring_line():
    assert parse_event("01.01.26 20:00:00;RING;0;030123456;") is None
