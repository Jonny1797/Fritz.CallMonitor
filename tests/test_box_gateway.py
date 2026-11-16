import pytest

from fritz_callhistory.config import Config
from fritz_callhistory.db.connection import connect
from fritz_callhistory.db.repository import (
    LocalPhonebookRepository,
    VoicemailMessageRecord,
)
from fritz_callhistory.fritz.client import (
    FritzPhonebookContact,
    FritzPhonebookNumber,
    VoicemailMessage,
)
from fritz_callhistory.fritz.exceptions import FritzBoxAuthError
from fritz_callhistory.sync.box_gateway import BoxGateway
from fritz_callhistory.sync.phonebook_io import import_from_box

from .fakes import FakeClient
from .test_sync_service import _make_call, _make_voicemail_message

_PATH = "/download.lua?path=/data/tam/rec/rec.0.003"
_DATE = "2026-06-01T10:00:00"


class Harness:
    def __init__(self, tmp_path, *, password="secret", client=None, config=None):
        self.client = client or FakeClient()
        self.created: list[tuple[str, str, str]] = []
        self.password = password
        self.gateway = BoxGateway(
            config or Config(address="192.168.178.1", username="admin"),
            db_path=tmp_path / "db.sqlite3",
            client_factory=self._factory,
            get_password=lambda user: self.password,
        )

    def _factory(self, address, user, password):
        self.created.append((address, user, password))
        return self.client


def _record(path=_PATH, date=_DATE, tam_index=0) -> VoicemailMessageRecord:
    return VoicemailMessageRecord(
        id=1,
        tam_index=tam_index,
        box_path=path,
        caller_number="0171 2345678",
        called_number="06898123456",
        message_date=date,
        duration_seconds=4,
        raw_name=None,
        is_new=True,
    )


def _box_message(box_index, path=_PATH, date=_DATE) -> VoicemailMessage:
    return _make_voicemail_message(box_index=box_index, path=path, date=date)


def test_has_credentials_needs_username_and_password(tmp_path):
    h = Harness(tmp_path, config=Config(username=""))
    assert not h.gateway.has_credentials
    h.gateway.apply_config(Config(username="admin"))
    assert h.gateway.has_credentials
    h.password = None
    h.gateway.apply_config(Config(username="admin"))
    assert not h.gateway.has_credentials


def test_has_credentials_flips_after_apply_config_once_password_exists(tmp_path):
    h = Harness(tmp_path, password=None, config=Config(username=""))
    h.gateway.apply_config(Config(username="admin"))
    assert not h.gateway.has_credentials
    h.password = "pw"
    h.gateway.apply_config(Config(username="admin"))
    assert h.gateway.has_credentials


def test_has_credentials_does_not_read_keyring(tmp_path):
    # has_credentials wird im GUI-Thread oft abgefragt - ein langsamer oder
    # gesperrter Schlüsselbund darf die Oberfläche nicht blockieren.
    lookups = []
    gateway = BoxGateway(
        Config(address="192.168.178.1", username="admin"),
        db_path=tmp_path / "db.sqlite3",
        client_factory=lambda *a: FakeClient(),
        get_password=lambda user: lookups.append(user) or "secret",
    )
    lookups.clear()

    for _ in range(3):
        assert gateway.has_credentials

    assert lookups == []


def test_config_property_returns_applied_config(tmp_path):
    h = Harness(tmp_path)
    new = Config(address="10.0.0.1", username="x")
    h.gateway.apply_config(new)
    assert h.gateway.config is new


def test_next_operation_uses_new_config_and_new_client_each_time(tmp_path):
    h = Harness(tmp_path)
    h.gateway.dial("123")
    h.gateway.apply_config(Config(address="10.0.0.2", username="other"))
    h.gateway.dial("456")
    assert h.created == [
        ("192.168.178.1", "admin", "secret"),
        ("10.0.0.2", "other", "secret"),
    ]


@pytest.mark.parametrize(
    "operation",
    [
        lambda g: g.sync(),
        lambda g: g.list_phonebooks(),
        lambda g: g.import_from_box([0]),
        lambda g: g.dial("1"),
        lambda g: g.voicemail_audio(_record()),
        lambda g: g.voicemail_mark_read(_record()),
        lambda g: g.voicemail_delete(_record()),
    ],
)
@pytest.mark.parametrize("missing", ["password", "username"])
def test_operations_without_credentials_raise_auth_error_and_build_no_client(
    tmp_path, operation, missing
):
    h = Harness(
        tmp_path,
        password=None if missing == "password" else "secret",
        config=Config(username="" if missing == "username" else "admin"),
    )
    with pytest.raises(FritzBoxAuthError):
        operation(h.gateway)
    assert h.created == []


def test_sync_writes_calls_phonebook_and_voicemail_and_returns_counts(tmp_path):
    client = FakeClient(
        calls=[_make_call(call_type=1, caller_number="0171 2345678", call_id=1)],
        phonebooks={0: [("Max Mustermann", ["0171 2345678"])]},
        voicemail_messages={0: [_box_message(0)]},
    )
    h = Harness(tmp_path, client=client)

    assert h.gateway.sync() == (1, 1)

    connection = connect(tmp_path / "db.sqlite3")
    try:
        assert connection.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM voicemail_messages").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM phonebook_entries").fetchone()[0] == 1
    finally:
        connection.close()


def test_sync_uses_phonebook_ids_from_config(tmp_path):
    client = FakeClient(phonebooks={0: [], 2: []})
    h = Harness(tmp_path, client=client, config=Config(username="admin", phonebook_ids=[2]))
    h.gateway.sync()
    assert [c for c in client.calls_made if c[0] == "phonebook_name_numbers"] == [
        ("phonebook_name_numbers", 2)
    ]


def test_list_phonebooks(tmp_path):
    h = Harness(tmp_path, client=FakeClient(phonebook_list=[(0, "Telefonbuch")]))
    assert h.gateway.list_phonebooks() == [(0, "Telefonbuch")]


def test_import_from_box_writes_contacts_and_counts(tmp_path):
    contact = FritzPhonebookContact(
        uniqueid="7",
        name="Max Mustermann",
        category="0",
        numbers=[FritzPhonebookNumber(value="0171 2345678", type="mobile")],
    )
    h = Harness(tmp_path, client=FakeClient(phonebook_contacts_detailed={0: [contact]}))

    assert h.gateway.import_from_box([0]) == 1

    connection = connect(tmp_path / "db.sqlite3")
    try:
        contacts = LocalPhonebookRepository(connection).list_all()
    finally:
        connection.close()
    assert [(c.display_name, c.box_uniqueid) for c in contacts] == [("Max Mustermann", "7")]


def test_dial(tmp_path):
    h = Harness(tmp_path)
    h.gateway.dial("+491234")
    assert ("dial_number", "+491234") in h.client.calls_made


def test_voicemail_audio_returns_audio_and_marks_read_at_looked_up_index(tmp_path):
    client = FakeClient(
        voicemail_messages={0: [_box_message(1, path="/other"), _box_message(5)]},
        audio=b"RIFF",
    )
    h = Harness(tmp_path, client=client)
    assert h.gateway.voicemail_audio(_record()) == b"RIFF"
    assert ("voicemail_audio", _PATH) in client.calls_made
    assert ("voicemail_mark_read", 0, 5) in client.calls_made


def test_voicemail_mark_read_and_delete_use_looked_up_index(tmp_path):
    client = FakeClient(voicemail_messages={0: [_box_message(7)]})
    h = Harness(tmp_path, client=client)
    h.gateway.voicemail_mark_read(_record())
    h.gateway.voicemail_delete(_record())
    assert ("voicemail_mark_read", 0, 7) in client.calls_made
    assert ("voicemail_delete", 0, 7) in client.calls_made


def test_voicemail_actions_do_nothing_when_message_is_gone(tmp_path):
    client = FakeClient(voicemail_messages={0: [_box_message(7, date="2026-01-01T00:00:00")]})
    h = Harness(tmp_path, client=client)
    h.gateway.voicemail_mark_read(_record())
    h.gateway.voicemail_delete(_record())
    h.gateway.voicemail_audio(_record())
    names = [c[0] for c in client.calls_made]
    assert "voicemail_mark_read" not in names
    assert "voicemail_delete" not in names


def test_check_credentials_uses_given_credentials_and_authenticated_call(tmp_path):
    h = Harness(tmp_path, password=None, config=Config(username=""))
    h.gateway.check_credentials("10.1.1.1", "bob", "pw")
    assert h.created == [("10.1.1.1", "bob", "pw")]
    assert ("get_calls", 1, None) in h.client.calls_made


# --- Import-Richtlinie (reine Funktion, In-Memory-SQLite) ---


def _box_contact(uniqueid, name, *numbers):
    return FritzPhonebookContact(
        uniqueid=uniqueid,
        name=name,
        category="0",
        numbers=[FritzPhonebookNumber(value=v, type=t) for v, t in numbers],
    )


def test_policy_creates_new_contact(connection):
    repo = LocalPhonebookRepository(connection)
    client = FakeClient(
        phonebook_contacts_detailed={0: [_box_contact("7", "Max", ("0171 2345678", "mobile"))]}
    )
    assert import_from_box(client, repo, [0]) == 1
    (contact,) = repo.list_all()
    assert (contact.display_name, contact.box_uniqueid) == ("Max", "7")
    assert [n.number_normalized for n in contact.numbers] == ["+491712345678"]


def test_policy_updates_by_uniqueid_keeping_notes_and_default_across_reimport(connection):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(
        display_name="Alt",
        notes="Notiz",
        numbers=[
            ("0171 2345678", "+491712345678", "mobile", False),
            ("030 1234567", "+49301234567", "home", True),
        ],
        box_uniqueid="7",
    )
    client = FakeClient(
        phonebook_contacts_detailed={
            0: [
                _box_contact(
                    "7", "Neu", ("0171 2345678", "mobile"), ("030 1234567", "home")
                )
            ]
        }
    )
    for _ in range(2):
        import_from_box(client, repo, [0])
    contact = repo.get(contact_id)
    assert contact.display_name == "Neu"
    assert contact.notes == "Notiz"
    assert {n.number_normalized: n.is_default for n in contact.numbers} == {
        "+491712345678": False,
        "+49301234567": True,
    }
    assert len(repo.list_all()) == 1


def test_policy_adopts_local_only_contact_with_same_number_set(connection):
    repo = LocalPhonebookRepository(connection)
    local_id = repo.create(
        display_name="Lokal",
        notes=None,
        numbers=[("0171 2345678", "+491712345678", "mobile", False)],
        box_uniqueid=None,
    )
    client = FakeClient(
        phonebook_contacts_detailed={0: [_box_contact("9", "Box", ("0171 2345678", "mobile"))]}
    )
    assert import_from_box(client, repo, [0]) == 1
    assert len(repo.list_all()) == 1
    assert repo.get(local_id).box_uniqueid == "9"


def test_policy_skips_nameless_contacts_and_drops_anonymous_numbers(connection):
    repo = LocalPhonebookRepository(connection)
    client = FakeClient(
        phonebook_contacts_detailed={
            0: [
                _box_contact("1", None, ("0171 2345678", "mobile")),
                _box_contact("2", "Anna", ("0171 2345678", "mobile"), ("", "home")),
            ]
        }
    )
    assert import_from_box(client, repo, [0]) == 1
    (contact,) = repo.list_all()
    assert contact.display_name == "Anna"
    assert len(contact.numbers) == 1


def test_policy_only_queries_selected_phonebook_ids(connection):
    client = FakeClient()
    import_from_box(client, LocalPhonebookRepository(connection), [2])
    assert client.calls_made == [("phonebook_contacts_detailed", 2)]
