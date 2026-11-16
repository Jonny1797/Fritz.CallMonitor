from fritz_callhistory.db.repository import (
    ContactRepository,
    LocalPhonebookRepository,
    PhonebookRepository,
)
from fritz_callhistory.sync.caller_directory import CallerDirectory


def _setup(connection):
    contacts = ContactRepository(connection)
    box = PhonebookRepository(connection)
    local = LocalPhonebookRepository(connection)
    return contacts, box, local, CallerDirectory(contacts, box, local)


def _local(local, name, number, notes=None):
    return local.create(display_name=name, notes=notes, numbers=[(number, number, "home", False)])


def test_telefonbuch_contact_beats_box_telefonbuch(connection):
    _, box, local, directory = _setup(connection)
    box.replace_entries(0, [("Box-Name", "+491761234567")])
    _local(local, "Lokal", "+491761234567")

    assert directory.identify("0176 1234567").name == "Lokal"


def test_box_telefonbuch_used_without_local_contact(connection):
    _, box, _, directory = _setup(connection)
    box.replace_entries(0, [("Box-Name", "+491761234567")])

    identity = directory.identify("+491761234567")

    assert identity.name == "Box-Name"
    assert identity.notes is None


def test_lowest_id_wins_for_name_and_notes(connection):
    _, _, local, directory = _setup(connection)
    _local(local, "Erster", "+491761234567", notes="n1")
    _local(local, "Zweiter", "+491761234567", notes="n2")

    identity = directory.identify("+491761234567")

    assert (identity.name, identity.notes) == ("Erster", "n1")


def test_anonymous_and_empty_share_one_anonymous_caller(connection):
    # Wie beim Sync: alle unterdrückten Nummern gehören zu einem Pseudo-Caller,
    # damit ein Doppelklick dessen Verlauf öffnen kann.
    contacts, _, _, directory = _setup(connection)
    assert directory.identify(None).caller_id is None

    ids = {directory.register(raw).caller_id for raw in (None, "", "  ")}

    assert len(ids) == 1 and None not in ids
    [anonymous] = contacts.search("")
    assert anonymous.is_anonymous and anonymous.id in ids
    identity = directory.identify("")
    assert identity.is_anonymous and identity.caller_id == anonymous.id


def test_identify_never_writes_but_register_creates_once(connection):
    contacts, _, _, directory = _setup(connection)

    assert directory.identify("+491761234567").caller_id is None
    assert contacts.search("") == []

    first = directory.register("+491761234567")
    second = directory.register("0176 1234567")

    assert first.caller_id is not None and second.caller_id == first.caller_id
    assert len(contacts.search("")) == 1
    assert directory.identify("+491761234567").caller_id == first.caller_id


def test_identify_many_uses_constant_number_of_queries(connection):
    contacts, _, _, directory = _setup(connection)
    numbers = [f"+4917600000{i:02d}" for i in range(30)]
    for number in numbers:
        contacts.upsert(number)
    statements: list[str] = []
    connection.set_trace_callback(statements.append)

    result = directory.identify_many(numbers)
    few = len(statements)
    statements.clear()
    directory.identify_many(numbers[:2])
    connection.set_trace_callback(None)

    assert len(result) == 30 and all(i.caller_id for i in result.values())
    assert few == len(statements)


def test_refresh_names_sets_and_clears(connection):
    contacts, _, local, directory = _setup(connection)
    contacts.upsert("+491761234567")
    contact_id = _local(local, "Lokal", "+491761234567")

    assert directory.refresh_names() == 1
    assert contacts.search("")[0].display_name == "Lokal"
    assert directory.refresh_names() == 0

    local.delete(contact_id)
    assert directory.refresh_names() == 1
    assert contacts.search("")[0].display_name is None


def test_matches_number_spellings_and_name(connection):
    _, box, _, directory = _setup(connection)
    box.replace_entries(0, [("Erika Muster", "+491761234567")])
    identity = directory.identify("+491761234567")

    for query in ("0176", "176", "+49176", "erika", "MUSTER"):
        assert directory.matches(query, identity), query
    for query in ("0177", "Hans"):
        assert not directory.matches(query, identity), query


def test_matches_agrees_with_sql_search(connection):
    contacts, _, _, directory = _setup(connection)
    contacts.upsert("+491761234567")
    identity = directory.identify("+491761234567")

    for query in ("0176", "00491761", "0177", "+49176", "xyz"):
        assert directory.matches(query, identity) == bool(contacts.search(query)), query


def test_label_order():
    from fritz_callhistory.sync.caller_directory import CallerIdentity

    named = CallerIdentity("+491761234567", False, "Name", None, None)
    unnamed = CallerIdentity("+491761234567", False, None, None, None)
    anonymous = CallerIdentity("anonymous", True, None, None, None)

    assert named.label("Fallback") == "Name"
    assert unnamed.label("Fallback") == "Fallback"
    assert unnamed.label() == "+49 176 1234567"
    assert anonymous.label() == "Anonym / unterdrückt"
