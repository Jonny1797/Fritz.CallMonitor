import pytest

from fritz_callhistory.db.repository import LocalPhonebookRepository
from fritz_callhistory.sync.phonebook_io import ImportResult
from fritz_callhistory.sync.telefonbuch import ContactDraft, NumberDraft, Telefonbuch


@pytest.fixture
def telefonbuch(connection):
    return Telefonbuch(connection)


def _draft(name="Max", *numbers, notes=None, box_uniqueid=None):
    return ContactDraft(
        display_name=name,
        notes=notes,
        numbers=[NumberDraft(*n) for n in numbers],
        box_uniqueid=box_uniqueid,
    )


# --- Schreiben: Bereinigung ---


def test_create_stores_one_row_for_numbers_equal_after_normalization(telefonbuch):
    contact_id = telefonbuch.create(
        _draft("Max", ("0301234567", "home"), ("+49 30 1234567", "mobile"))
    )

    (number,) = telefonbuch.get(contact_id).numbers
    assert (number.number_raw, number.number_normalized, number.number_type) == (
        "0301234567",
        "+49301234567",
        "home",
    )


def test_create_drops_anonymous_numbers(telefonbuch):
    contact_id = telefonbuch.create(_draft("Max", ("", "home"), ("0301234567", "home")))

    assert [n.number_normalized for n in telefonbuch.get(contact_id).numbers] == ["+49301234567"]


def test_duplicate_keeps_the_first_numbers_default_flag(telefonbuch):
    contact_id = telefonbuch.create(
        _draft("Max", ("0301234567", "home", False), ("+49301234567", "home", True))
    )

    (number,) = telefonbuch.get(contact_id).numbers
    assert number.is_default is False


def test_only_the_first_marked_number_becomes_default(telefonbuch):
    contact_id = telefonbuch.create(
        _draft(
            "Max",
            ("0301111111", "home", False),
            ("0302222222", "home", True),
            ("0303333333", "home", True),
        )
    )

    assert [n.is_default for n in telefonbuch.get(contact_id).numbers] == [False, True, False]


def test_single_number_is_not_made_default_automatically(telefonbuch):
    contact_id = telefonbuch.create(_draft("Max", ("0301234567", "home")))

    assert [n.is_default for n in telefonbuch.get(contact_id).numbers] == [False]


def test_update_keeps_row_ids_of_unchanged_numbers(telefonbuch):
    contact_id = telefonbuch.create(
        _draft("Max", ("0301111111", "home"), ("0302222222", "home"), ("0303333333", "home"))
    )
    before = {n.number_normalized: n.id for n in telefonbuch.get(contact_id).numbers}

    telefonbuch.update(
        contact_id,
        _draft(
            "Maximilian",
            ("0301111111", "home"),
            ("0302222222", "mobile"),  # Typ geändert
            ("0304444444", "work"),  # neu; 0303333333 entfällt
        ),
    )

    contact = telefonbuch.get(contact_id)
    after = {n.number_normalized: n for n in contact.numbers}
    assert contact.display_name == "Maximilian"
    assert set(after) == {"+49301111111", "+49302222222", "+49304444444"}
    assert after["+49301111111"].id == before["+49301111111"]
    assert after["+49302222222"].id == before["+49302222222"]
    assert after["+49302222222"].number_type == "mobile"


def test_update_cleans_up_legacy_duplicate_rows(telefonbuch, connection):
    contact_id = LocalPhonebookRepository(connection).create(
        display_name="Max",
        notes=None,
        numbers=[
            ("0301234567", "+49301234567", "home", False),
            ("+49 30 1234567", "+49301234567", "home", False),
        ],
    )

    telefonbuch.update(contact_id, _draft("Max", ("0301234567", "home")))

    assert len(telefonbuch.get(contact_id).numbers) == 1


def test_delete_removes_contact(telefonbuch):
    contact_id = telefonbuch.create(_draft("Max", ("0301234567", "home")))
    telefonbuch.delete(contact_id)
    assert telefonbuch.get(contact_id) is None


def test_find_by_number_normalizes_and_returns_none_for_anonymous(telefonbuch):
    contact_id = telefonbuch.create(_draft("Max", ("0301234567", "home")))

    assert telefonbuch.find_by_number("+49 30 1234567").id == contact_id
    assert telefonbuch.find_by_number("") is None
    assert telefonbuch.find_by_number("0309999999") is None


# --- Datei-Import (Import-Duplikat) ---


def test_import_file_creates_contacts_and_passes_warnings(telefonbuch):
    result = ImportResult(
        contacts=[_draft("A", ("0301111111", "home")), _draft("B")], warnings=["Hinweis"]
    )

    summary = telefonbuch.import_file(result)

    assert (summary.created, summary.skipped_duplicate, summary.warnings) == (2, 0, ["Hinweis"])
    assert len(telefonbuch.list()) == 2


def test_import_file_twice_skips_duplicates_on_second_run(telefonbuch):
    result = ImportResult(
        contacts=[_draft("A", ("0301111111", "home")), _draft("B", ("0302222222", "home"))]
    )
    telefonbuch.import_file(result)

    second = telefonbuch.import_file(result)

    assert (second.created, second.skipped_duplicate) == (0, 2)
    assert len(telefonbuch.list()) == 2


def test_import_file_recreates_name_only_contacts(telefonbuch):
    result = ImportResult(contacts=[_draft("Nur Name")])
    telefonbuch.import_file(result)

    second = telefonbuch.import_file(result)

    assert (second.created, second.skipped_duplicate) == (1, 0)


def test_import_file_partial_number_overlap_is_not_a_duplicate(telefonbuch):
    telefonbuch.create(_draft("A", ("0301111111", "home"), ("0302222222", "home")))

    summary = telefonbuch.import_file(ImportResult(contacts=[_draft("B", ("0301111111", "home"))]))

    assert summary.created == 1


def test_import_file_stores_number_listed_twice_once(telefonbuch):
    telefonbuch.import_file(
        ImportResult(contacts=[_draft("A", ("0301111111", "home"), ("+49 30 1111111", "work"))])
    )

    (contact,) = telefonbuch.list()
    assert len(contact.numbers) == 1


def test_import_file_failing_midway_stores_nothing(telefonbuch, mocker):
    result = ImportResult(
        contacts=[_draft("A", ("0301111111", "home")), _draft("B", ("0302222222", "home"))]
    )
    original = LocalPhonebookRepository.create
    calls = []

    def flaky(self, **kwargs):
        calls.append(kwargs["display_name"])
        if len(calls) == 2:
            raise RuntimeError("Absturz mitten im Import")
        return original(self, **kwargs)

    mocker.patch.object(LocalPhonebookRepository, "create", flaky)

    with pytest.raises(RuntimeError):
        telefonbuch.import_file(result)

    assert telefonbuch.list() == []


# --- Box-Import ---


def test_box_import_creates_new_contact_with_box_id(telefonbuch):
    assert telefonbuch.import_box_contacts(
        [_draft("Max", ("0171 2345678", "mobile"), box_uniqueid="7")]
    ) == 1

    (contact,) = telefonbuch.list()
    assert (contact.display_name, contact.box_uniqueid) == ("Max", "7")
    assert [n.number_normalized for n in contact.numbers] == ["+491712345678"]


def test_box_reimport_keeps_notes_and_default_while_number_is_still_on_box(telefonbuch):
    contact_id = LocalPhonebookRepository(telefonbuch._conn).create(
        display_name="Alt",
        notes="Notiz",
        numbers=[
            ("0171 2345678", "+491712345678", "mobile", False),
            ("030 1234567", "+49301234567", "home", True),
        ],
        box_uniqueid="7",
    )
    drafts = [
        _draft("Neu", ("0171 2345678", "mobile"), ("030 1234567", "home"), box_uniqueid="7")
    ]

    telefonbuch.import_box_contacts(drafts)
    telefonbuch.import_box_contacts(drafts)

    contact = telefonbuch.get(contact_id)
    assert (contact.display_name, contact.notes) == ("Neu", "Notiz")
    assert {n.number_normalized: n.is_default for n in contact.numbers} == {
        "+491712345678": False,
        "+49301234567": True,
    }
    assert len(telefonbuch.list()) == 1


def test_box_reimport_drops_default_when_number_left_the_box(telefonbuch):
    contact_id = telefonbuch.create(
        _draft("Max", ("0301111111", "home", True), ("0302222222", "home"), box_uniqueid="7")
    )

    telefonbuch.import_box_contacts([_draft("Max", ("0302222222", "home"), box_uniqueid="7")])

    assert [n.is_default for n in telefonbuch.get(contact_id).numbers] == [False]


def test_box_import_adopts_contact_without_box_id_with_same_number_set(telefonbuch):
    local_id = telefonbuch.create(_draft("Lokal", ("0171 2345678", "mobile")))

    telefonbuch.import_box_contacts([_draft("Box", ("0171 2345678", "mobile"), box_uniqueid="9")])

    assert len(telefonbuch.list()) == 1
    assert telefonbuch.get(local_id).box_uniqueid == "9"


def test_box_import_never_adopts_contact_that_already_has_a_box_id(telefonbuch):
    telefonbuch.create(_draft("Eins", ("0171 2345678", "mobile"), box_uniqueid="1"))

    telefonbuch.import_box_contacts([_draft("Zwei", ("0171 2345678", "mobile"), box_uniqueid="2")])

    assert sorted(c.box_uniqueid for c in telefonbuch.list()) == ["1", "2"]


def test_box_import_does_not_adopt_on_partial_number_overlap(telefonbuch):
    telefonbuch.create(_draft("Lokal", ("0301111111", "home"), ("0302222222", "home")))

    telefonbuch.import_box_contacts([_draft("Box", ("0301111111", "home"), box_uniqueid="9")])

    assert len(telefonbuch.list()) == 2


def test_box_import_skips_nameless_drafts_and_drops_anonymous_numbers(telefonbuch):
    count = telefonbuch.import_box_contacts(
        [
            _draft("", ("0171 2345678", "mobile"), box_uniqueid="1"),
            _draft("Anna", ("0171 2345678", "mobile"), ("", "home"), box_uniqueid="2"),
        ]
    )

    assert count == 1
    (contact,) = telefonbuch.list()
    assert (contact.display_name, len(contact.numbers)) == ("Anna", 1)


def test_box_import_failing_midway_stores_nothing(telefonbuch, mocker):
    original = LocalPhonebookRepository.create
    calls = []

    def flaky(self, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Absturz")
        return original(self, **kwargs)

    mocker.patch.object(LocalPhonebookRepository, "create", flaky)

    with pytest.raises(RuntimeError):
        telefonbuch.import_box_contacts(
            [
                _draft("A", ("0301111111", "home"), box_uniqueid="1"),
                _draft("B", ("0302222222", "home"), box_uniqueid="2"),
            ]
        )

    assert telefonbuch.list() == []


def test_exact_number_lookup_runs_one_query_regardless_of_number_count(connection):
    repo = LocalPhonebookRepository(connection)
    numbers = {f"+4930{i:07d}" for i in range(50)}
    statements = []
    connection.set_trace_callback(statements.append)

    repo.find_ids_by_exact_numbers(numbers)

    connection.set_trace_callback(None)
    assert len(statements) == 1


def test_vcard_listing_the_same_tel_twice_is_stored_once(telefonbuch, tmp_path):
    from fritz_callhistory.sync.phonebook_io import parse_vcard

    path = tmp_path / "c.vcf"
    path.write_text(
        "BEGIN:VCARD\nVERSION:3.0\nFN:Max\nTEL;TYPE=HOME:0301234567\n"
        "TEL;TYPE=CELL:+49 30 1234567\nEND:VCARD\n"
    )

    telefonbuch.import_file(parse_vcard(path))

    (contact,) = telefonbuch.list()
    assert len(contact.numbers) == 1
