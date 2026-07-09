import pytest
from fritzconnection.core.exceptions import FritzAuthorizationError, FritzConnectionException

from fritz_callhistory.fritz.client import FritzBoxClient, _retry_network
from fritz_callhistory.fritz.exceptions import (
    FritzBoxConnectionError,
    FritzBoxPermissionError,
)


@pytest.fixture(autouse=True)
def no_real_sleep(mocker):
    # Retries sollen in Tests nicht tatsächlich warten.
    mocker.patch("fritz_callhistory.fritz.client.time.sleep")


def test_retry_network_retries_once_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise FritzConnectionException("timeout")
        return "ok"

    assert _retry_network(flaky) == "ok"
    assert len(calls) == 2


def test_retry_network_raises_after_max_attempts():
    calls = []

    def always_fails():
        calls.append(1)
        raise FritzConnectionException("still down")

    with pytest.raises(FritzConnectionException):
        _retry_network(always_fails)
    assert len(calls) == 2


def test_retry_network_does_not_retry_auth_error():
    calls = []

    def auth_fails():
        calls.append(1)
        raise FritzAuthorizationError("nope")

    with pytest.raises(FritzAuthorizationError):
        _retry_network(auth_fails)
    assert len(calls) == 1


def _make_client(call=None, phonebook=None, connection=None) -> FritzBoxClient:
    client = FritzBoxClient.__new__(FritzBoxClient)
    client._call = call
    client._phonebook = phonebook
    client._connection = connection
    return client


def test_get_calls_translates_permission_error(mocker):
    fake_call = mocker.Mock()
    fake_call.get_calls.side_effect = FritzAuthorizationError("forbidden")
    client = _make_client(call=fake_call)

    with pytest.raises(FritzBoxPermissionError):
        client.get_calls()


def test_get_calls_translates_connection_error_after_retry(mocker):
    fake_call = mocker.Mock()
    fake_call.get_calls.side_effect = FritzConnectionException("down")
    client = _make_client(call=fake_call)

    with pytest.raises(FritzBoxConnectionError):
        client.get_calls()
    assert fake_call.get_calls.call_count == 2


def test_get_calls_returns_result_on_success(mocker):
    fake_call = mocker.Mock()
    fake_call.get_calls.return_value = ["call-1"]
    client = _make_client(call=fake_call)

    assert client.get_calls() == ["call-1"]


def test_dial_number_passes_number_through_on_success(mocker):
    fake_call = mocker.Mock()
    client = _make_client(call=fake_call)

    client.dial_number("+491234567")

    fake_call.dial.assert_called_once_with("+491234567")


def test_dial_number_translates_permission_error(mocker):
    fake_call = mocker.Mock()
    fake_call.dial.side_effect = FritzAuthorizationError("forbidden")
    client = _make_client(call=fake_call)

    with pytest.raises(FritzBoxPermissionError):
        client.dial_number("+491234567")


def test_dial_number_translates_connection_error_after_retry(mocker):
    fake_call = mocker.Mock()
    fake_call.dial.side_effect = FritzConnectionException("down")
    client = _make_client(call=fake_call)

    with pytest.raises(FritzBoxConnectionError):
        client.dial_number("+491234567")
    assert fake_call.dial.call_count == 2


def test_phonebook_ids_translates_connection_error(mocker):
    fake_phonebook = mocker.Mock()
    type(fake_phonebook).phonebook_ids = mocker.PropertyMock(
        side_effect=FritzConnectionException("down")
    )
    client = _make_client(phonebook=fake_phonebook)

    with pytest.raises(FritzBoxConnectionError):
        client.phonebook_ids()


_PHONEBOOK_XML = """<?xml version="1.0" encoding="utf-8"?>
<phonebooks>
  <phonebook name="Telefonbuch">
    <contact>
      <category>0</category>
      <person><realName>Max Mustermann</realName></person>
      <telephony nid="2">
        <number type="mobile" prio="1" id="0">+491234567</number>
        <number type="home" prio="0" id="1">03012345678</number>
      </telephony>
      <uniqueid>7</uniqueid>
    </contact>
    <contact>
      <category>0</category>
      <person><realName>Ohne Nummer</realName></person>
      <telephony nid="1" />
    </contact>
  </phonebook>
</phonebooks>
"""


def test_phonebook_contacts_detailed_parses_uniqueid_and_number_type(mocker, tmp_path):
    # get_xml_root akzeptiert auch Dateipfade als "source" - spart einen echten
    # HTTP-Mock fuer diesen Test.
    xml_path = tmp_path / "phonebook.xml"
    xml_path.write_text(_PHONEBOOK_XML)

    fake_phonebook = mocker.Mock()
    fake_phonebook.phonebook_info.return_value = {"url": str(xml_path)}
    fake_connection = mocker.Mock()
    client = _make_client(phonebook=fake_phonebook, connection=fake_connection)

    contacts = client.phonebook_contacts_detailed(0)

    assert len(contacts) == 2
    first = contacts[0]
    assert first.name == "Max Mustermann"
    assert first.uniqueid == "7"
    assert [(n.value, n.type) for n in first.numbers] == [
        ("+491234567", "mobile"),
        ("03012345678", "home"),
    ]
    second = contacts[1]
    assert second.name == "Ohne Nummer"
    assert second.uniqueid is None
    assert second.numbers == []


def test_phonebook_contacts_detailed_translates_connection_error(mocker):
    fake_phonebook = mocker.Mock()
    fake_phonebook.phonebook_info.side_effect = FritzConnectionException("down")
    client = _make_client(phonebook=fake_phonebook, connection=mocker.Mock())

    with pytest.raises(FritzBoxConnectionError):
        client.phonebook_contacts_detailed(0)


_VOICEMAIL_TAM_LIST_XML = (
    "<List><TAMRunning>1</TAMRunning><Item><Index>0</Index><Enable>1</Enable>"
    "<Name>Anrufbeantworter</Name></Item><Item><Index>1</Index><Enable>0</Enable>"
    "<Name></Name></Item></List>"
)

_VOICEMAIL_MESSAGE_LIST_XML = """<?xml version="1.0" encoding="utf-8"?>
<Root>
<Message>
<Index>0</Index>
<Tam>0</Tam>
<Called>65831249</Called>
<Date>09.07.26 16:43</Date>
<Duration>0:04</Duration>
<Inbook>1</Inbook>
<Name>Georg</Name>
<New>1</New>
<Number>015905094489</Number>
<Path>/download.lua?path=/data/tam/rec/rec.0.000</Path>
</Message>
</Root>
"""


def test_voicemail_tam_indices_returns_only_enabled_slots(mocker):
    fake_connection = mocker.Mock()
    fake_connection.call_action.return_value = {"NewTAMList": _VOICEMAIL_TAM_LIST_XML}
    client = _make_client(connection=fake_connection)

    assert client.voicemail_tam_indices() == [0]
    fake_connection.call_action.assert_called_once_with("X_AVM-DE_TAM", "GetList")


def test_voicemail_tam_indices_translates_permission_error(mocker):
    fake_connection = mocker.Mock()
    fake_connection.call_action.side_effect = FritzAuthorizationError("forbidden")
    client = _make_client(connection=fake_connection)

    with pytest.raises(FritzBoxPermissionError):
        client.voicemail_tam_indices()


def test_voicemail_tam_indices_translates_connection_error(mocker):
    fake_connection = mocker.Mock()
    fake_connection.call_action.side_effect = FritzConnectionException("down")
    client = _make_client(connection=fake_connection)

    with pytest.raises(FritzBoxConnectionError):
        client.voicemail_tam_indices()


def test_voicemail_messages_parses_xml_fields(mocker, tmp_path):
    xml_path = tmp_path / "messages.xml"
    xml_path.write_text(_VOICEMAIL_MESSAGE_LIST_XML)

    fake_connection = mocker.Mock()
    fake_connection.call_action.return_value = {"NewURL": str(xml_path)}
    client = _make_client(connection=fake_connection)

    messages = client.voicemail_messages(0)

    assert len(messages) == 1
    message = messages[0]
    assert message.tam_index == 0
    assert message.box_index == 0
    assert message.caller_number == "015905094489"
    assert message.called_number == "65831249"
    assert message.date == "2026-07-09T16:43:00"
    assert message.duration_seconds == 4
    assert message.name == "Georg"
    assert message.path == "/download.lua?path=/data/tam/rec/rec.0.000"
    assert message.is_new is True
    fake_connection.call_action.assert_called_once_with(
        "X_AVM-DE_TAM", "GetMessageList", NewIndex=0
    )


def test_voicemail_messages_translates_permission_error(mocker):
    fake_connection = mocker.Mock()
    fake_connection.call_action.side_effect = FritzAuthorizationError("forbidden")
    client = _make_client(connection=fake_connection)

    with pytest.raises(FritzBoxPermissionError):
        client.voicemail_messages(0)


def test_voicemail_audio_fetches_bytes_via_http_interface(mocker):
    fake_response = mocker.Mock()
    fake_response.content = b"RIFF..."
    fake_connection = mocker.Mock()
    fake_connection.address = "http://192.168.100.1"
    fake_connection.port = 49000
    fake_connection.http_interface.call_url.return_value = fake_response
    client = _make_client(connection=fake_connection)

    audio = client.voicemail_audio("/download.lua?path=/data/tam/rec/rec.0.000")

    assert audio == b"RIFF..."
    fake_connection.http_interface.call_url.assert_called_once_with(
        "http://192.168.100.1:49000/download.lua",
        {"path": "/data/tam/rec/rec.0.000"},
    )


def test_voicemail_audio_translates_connection_error(mocker):
    fake_connection = mocker.Mock()
    fake_connection.address = "http://192.168.100.1"
    fake_connection.port = 49000
    fake_connection.http_interface.call_url.side_effect = FritzConnectionException("down")
    client = _make_client(connection=fake_connection)

    with pytest.raises(FritzBoxConnectionError):
        client.voicemail_audio("/download.lua?path=/data/tam/rec/rec.0.000")


def test_voicemail_mark_read_calls_mark_message_action(mocker):
    fake_connection = mocker.Mock()
    client = _make_client(connection=fake_connection)

    client.voicemail_mark_read(0, 3)

    fake_connection.call_action.assert_called_once_with(
        "X_AVM-DE_TAM", "MarkMessage", NewIndex=0, NewMessageIndex=3, NewMarkedAsRead=1
    )


def test_voicemail_mark_read_translates_permission_error(mocker):
    fake_connection = mocker.Mock()
    fake_connection.call_action.side_effect = FritzAuthorizationError("forbidden")
    client = _make_client(connection=fake_connection)

    with pytest.raises(FritzBoxPermissionError):
        client.voicemail_mark_read(0, 3)
