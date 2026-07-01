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


def _make_client(call=None, phonebook=None) -> FritzBoxClient:
    client = FritzBoxClient.__new__(FritzBoxClient)
    client._call = call
    client._phonebook = phonebook
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


def test_phonebook_ids_translates_connection_error(mocker):
    fake_phonebook = mocker.Mock()
    type(fake_phonebook).phonebook_ids = mocker.PropertyMock(
        side_effect=FritzConnectionException("down")
    )
    client = _make_client(phonebook=fake_phonebook)

    with pytest.raises(FritzBoxConnectionError):
        client.phonebook_ids()
