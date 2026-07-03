from fritz_callhistory.db.repository import (
    CallRepository,
    ContactRepository,
    LocalPhonebookRepository,
    SyncStateRepository,
)


def test_upsert_contact_is_idempotent(connection):
    contacts = ContactRepository(connection)
    id_first = contacts.upsert("+491234567")
    id_second = contacts.upsert("+491234567")
    assert id_first == id_second


def test_contact_search_matches_name_and_number(connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    assert [c.id for c in contacts.search("Mustermann")] == [contact_id]
    assert [c.id for c in contacts.search("1234567")] == [contact_id]
    assert contacts.search("does-not-exist") == []


def test_find_by_number_returns_matching_contact(connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    contacts.upsert("+499876543")

    found = contacts.find_by_number("+491234567")

    assert found is not None
    assert found.id == contact_id
    assert found.display_name == "Max Mustermann"


def test_find_by_number_returns_none_when_missing(connection):
    contacts = ContactRepository(connection)
    assert contacts.find_by_number("+491234567") is None


def test_call_insert_dedupes_on_natural_key(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")

    call_kwargs = dict(
        contact_id=contact_id,
        call_type=1,
        caller_number="+491234567",
        called_number="+4900000000",
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=42,
        raw_name="Max Mustermann",
    )

    assert calls.insert(**call_kwargs) is True
    # Erneuter Sync desselben Anrufs darf keinen Duplikat-Eintrag erzeugen.
    assert calls.insert(**call_kwargs) is False

    records = calls.for_contact(contact_id)
    assert len(records) == 1
    assert records[0].duration_seconds == 42


def test_calls_for_contact_ordered_newest_first(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")

    for i, date in enumerate(["2026-06-01T10:00:00", "2026-06-03T10:00:00", "2026-06-02T10:00:00"]):
        calls.insert(
            contact_id=contact_id,
            call_type=1,
            caller_number="+491234567",
            called_number=None,
            port=None,
            device=None,
            call_date=date,
            duration_seconds=i,
            raw_name=None,
        )

    records = calls.for_contact(contact_id)
    assert [r.call_date for r in records] == [
        "2026-06-03T10:00:00",
        "2026-06-02T10:00:00",
        "2026-06-01T10:00:00",
    ]


def _insert_call(calls, *, contact_id, call_date, call_type=1, duration_seconds=0, box_call_id=None):
    calls.insert(
        contact_id=contact_id,
        call_type=call_type,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date=call_date,
        duration_seconds=duration_seconds,
        raw_name=None,
        box_call_id=box_call_id,
    )


def test_all_calls_returns_calls_with_contact_info(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00")

    results = calls.all_calls()

    assert len(results) == 1
    assert results[0].contact_display_name == "Max Mustermann"
    assert results[0].contact_primary_number == "+491234567"
    assert results[0].contact_is_anonymous is False


def test_all_calls_ordered_newest_first_across_contacts(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_a = contacts.upsert("+491111111")
    contact_b = contacts.upsert("+492222222")
    _insert_call(calls, contact_id=contact_a, call_date="2026-06-01T10:00:00")
    _insert_call(calls, contact_id=contact_b, call_date="2026-06-03T10:00:00")
    _insert_call(calls, contact_id=contact_a, call_date="2026-06-02T10:00:00")

    results = calls.all_calls()

    assert [r.call_date for r in results] == [
        "2026-06-03T10:00:00",
        "2026-06-02T10:00:00",
        "2026-06-01T10:00:00",
    ]


def test_all_calls_includes_anonymous_contact(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("anonymous", is_anonymous=True)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00")

    results = calls.all_calls()

    assert results[0].contact_is_anonymous is True
    assert results[0].contact_display_name is None


def test_all_calls_filters_by_date_from_inclusive(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T00:00:00")

    results = calls.all_calls(date_from="2026-06-01T00:00:00")

    assert len(results) == 1


def test_all_calls_filters_by_date_to_inclusive(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T23:59:59")

    results = calls.all_calls(date_to="2026-06-01T23:59:59")

    assert len(results) == 1


def test_all_calls_excludes_calls_outside_range(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-05-31T23:59:59")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T12:00:00")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-03T00:00:00")

    results = calls.all_calls(date_from="2026-06-01T00:00:00", date_to="2026-06-02T23:59:59")

    assert [r.call_date for r in results] == ["2026-06-01T12:00:00"]


def test_all_calls_returns_everything_when_no_filter_given(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-01-01T00:00:00")
    _insert_call(calls, contact_id=contact_id, call_date="2026-12-31T23:59:59")

    results = calls.all_calls()

    assert len(results) == 2


def test_all_calls_filters_by_call_types_single(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00", call_type=1)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-02T10:00:00", call_type=2)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-03T10:00:00", call_type=3)

    results = calls.all_calls(call_types=[2])

    assert len(results) == 1
    assert results[0].call_type == 2


def test_all_calls_filters_by_call_types_multiple(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00", call_type=1)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-02T10:00:00", call_type=2)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-03T10:00:00", call_type=10)

    results = calls.all_calls(call_types=[2, 10])

    assert {r.call_type for r in results} == {2, 10}


def test_all_calls_call_types_combined_with_date_from(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00", call_type=2)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-05T10:00:00", call_type=2)

    results = calls.all_calls(date_from="2026-06-03T00:00:00", call_types=[2])

    assert [r.call_date for r in results] == ["2026-06-05T10:00:00"]


def test_all_calls_call_types_none_or_empty_returns_all(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00", call_type=1)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-02T10:00:00", call_type=2)

    assert len(calls.all_calls(call_types=None)) == 2
    assert len(calls.all_calls(call_types=[])) == 2


def test_all_calls_breaks_ties_on_same_call_date_by_box_call_id(connection):
    # Zwei Anrufe in derselben Minute (call_date hat nur Minutengenauigkeit,
    # siehe Migration 002) - box_call_id muss die tatsaechliche Reihenfolge
    # wiederherstellen (hoehere Id = neuer, empirisch gegen echte Box verifiziert).
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    # Unterschiedliche duration_seconds, damit die beiden Anrufe nicht ueber
    # den Dedupe-Unique-Index (call_date, Nummern, duration_seconds) als
    # derselbe Anruf zusammenfallen - realistisch fuer zwei echte Anrufe.
    _insert_call(
        calls,
        contact_id=contact_id,
        call_date="2026-07-02T17:11:00",
        call_type=2,
        duration_seconds=0,
        box_call_id=39,
    )
    _insert_call(
        calls,
        contact_id=contact_id,
        call_date="2026-07-02T17:11:00",
        call_type=1,
        duration_seconds=42,
        box_call_id=40,
    )

    results = calls.all_calls()

    assert [r.box_call_id for r in results] == [40, 39]


def test_for_contact_breaks_ties_on_same_call_date_by_box_call_id(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(
        calls,
        contact_id=contact_id,
        call_date="2026-07-02T17:11:00",
        call_type=2,
        duration_seconds=0,
        box_call_id=39,
    )
    _insert_call(
        calls,
        contact_id=contact_id,
        call_date="2026-07-02T17:11:00",
        call_type=1,
        duration_seconds=42,
        box_call_id=40,
    )

    records = calls.for_contact(contact_id)

    assert [r.box_call_id for r in records] == [40, 39]


def test_all_calls_orders_pre_migration_rows_without_box_call_id_last(connection):
    # Vor dieser Aenderung synchronisierte Anrufe haben box_call_id=NULL - bei
    # Gleichstand mit call_date darf das nicht crashen, auch wenn die
    # Reihenfolge unter ihnen dann unbestimmt bleibt.
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-07-02T17:11:00", box_call_id=None)
    _insert_call(calls, contact_id=contact_id, call_date="2026-07-02T17:10:00", box_call_id=None)

    results = calls.all_calls()

    assert [r.call_date for r in results] == ["2026-07-02T17:11:00", "2026-07-02T17:10:00"]


def test_sync_state_roundtrip(connection):
    state = SyncStateRepository(connection)
    assert state.get("last_sync_at") is None
    state.set("last_sync_at", "2026-06-01T10:00:00")
    assert state.get("last_sync_at") == "2026-06-01T10:00:00"
    state.set("last_sync_at", "2026-06-02T10:00:00")
    assert state.get("last_sync_at") == "2026-06-02T10:00:00"


def test_local_phonebook_create_and_get_round_trip(connection):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(
        display_name="Max Mustermann",
        notes="VIP",
        numbers=[("0171 2345678", "+491712345678", "mobile"), ("030 1234567", "+49301234567", "home")],
    )

    contact = repo.get(contact_id)

    assert contact.display_name == "Max Mustermann"
    assert contact.notes == "VIP"
    assert contact.box_uniqueid is None
    assert [(n.number_raw, n.number_normalized, n.number_type) for n in contact.numbers] == [
        ("0171 2345678", "+491712345678", "mobile"),
        ("030 1234567", "+49301234567", "home"),
    ]


def test_local_phonebook_get_missing_returns_none(connection):
    repo = LocalPhonebookRepository(connection)
    assert repo.get(999) is None


def test_local_phonebook_create_with_zero_numbers_is_allowed(connection):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(display_name="Nur ein Name", notes=None, numbers=[])
    assert repo.get(contact_id).numbers == []


def test_local_phonebook_update_replaces_numbers(connection):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(
        display_name="Max Mustermann", notes=None, numbers=[("+491234567", "+491234567", "home")]
    )

    repo.update(
        contact_id,
        display_name="Max M.",
        notes="Neue Notiz",
        numbers=[("+499876543", "+499876543", "mobile")],
    )

    contact = repo.get(contact_id)
    assert contact.display_name == "Max M."
    assert contact.notes == "Neue Notiz"
    assert [n.number_normalized for n in contact.numbers] == ["+499876543"]


def test_local_phonebook_delete_removes_contact_and_numbers(connection):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(
        display_name="Max Mustermann", notes=None, numbers=[("+491234567", "+491234567", "home")]
    )

    repo.delete(contact_id)

    assert repo.get(contact_id) is None
    row = connection.execute(
        "SELECT COUNT(*) FROM phonebook_contact_numbers WHERE phonebook_contact_id = ?", (contact_id,)
    ).fetchone()
    assert row[0] == 0


def test_local_phonebook_lookup_name_ties_break_by_lowest_id(connection):
    repo = LocalPhonebookRepository(connection)
    repo.create(display_name="Erster", notes=None, numbers=[("+491234567", "+491234567", "home")])
    repo.create(display_name="Zweiter", notes=None, numbers=[("+491234567", "+491234567", "home")])

    assert repo.lookup_name("+491234567") == "Erster"


def test_local_phonebook_lookup_name_returns_none_when_missing(connection):
    repo = LocalPhonebookRepository(connection)
    assert repo.lookup_name("+491234567") is None


def test_local_phonebook_box_uniqueid_round_trip(connection):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(display_name="Max Mustermann", notes=None, numbers=[])

    assert repo.find_by_box_uniqueid("7") is None
    repo.set_box_uniqueid(contact_id, "7")

    found = repo.find_by_box_uniqueid("7")
    assert found is not None
    assert found.id == contact_id


def test_all_numbers_belong_to_one_contact_true_for_exact_match(connection):
    repo = LocalPhonebookRepository(connection)
    repo.create(
        display_name="Max Mustermann",
        notes=None,
        numbers=[("+491234567", "+491234567", "home"), ("+499876543", "+499876543", "mobile")],
    )

    assert repo.all_numbers_belong_to_one_contact(["+491234567", "+499876543"]) is True


def test_all_numbers_belong_to_one_contact_false_for_partial_overlap(connection):
    repo = LocalPhonebookRepository(connection)
    repo.create(display_name="Max Mustermann", notes=None, numbers=[("+491234567", "+491234567", "home")])
    repo.create(display_name="Erika Musterfrau", notes=None, numbers=[("+499876543", "+499876543", "home")])

    assert repo.all_numbers_belong_to_one_contact(["+491234567", "+499876543"]) is False


def test_all_numbers_belong_to_one_contact_false_for_empty_list(connection):
    repo = LocalPhonebookRepository(connection)
    assert repo.all_numbers_belong_to_one_contact([]) is False


def test_find_local_only_contact_by_exact_numbers_matches_local_contact(connection):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(
        display_name="Max Mustermann", notes=None, numbers=[("+491234567", "+491234567", "home")]
    )

    found = repo.find_local_only_contact_by_exact_numbers(["+491234567"])

    assert found == contact_id


def test_find_local_only_contact_by_exact_numbers_ignores_box_linked_contacts(connection):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(
        display_name="Max Mustermann",
        notes=None,
        numbers=[("+491234567", "+491234567", "home")],
        box_uniqueid="7",
    )

    assert repo.find_local_only_contact_by_exact_numbers(["+491234567"]) is None
    assert contact_id is not None  # sanity: der Kontakt existiert tatsaechlich
