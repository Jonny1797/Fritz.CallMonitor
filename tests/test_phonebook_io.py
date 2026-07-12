import pytest

from fritz_callhistory.db.repository import LocalPhonebookRepository
from fritz_callhistory.sync.phonebook_io import (
    ImportedContact,
    ImportedNumber,
    ImportResult,
    PhonebookImportError,
    import_contacts,
    parse_csv,
    parse_vcard,
    parse_xml,
    write_csv,
    write_vcard,
    write_xml,
)

_CONTACTS = [
    ImportedContact(
        display_name="Max Mustermann",
        notes="VIP",
        numbers=[
            ImportedNumber("+491234567", "+491234567", "mobile"),
            ImportedNumber("03012345678", "+493012345678", "home"),
        ],
        box_uniqueid="7",
    ),
    ImportedContact(display_name="Erika Musterfrau", notes=None, numbers=[]),
]


# --- XML ---


def test_xml_write_then_parse_round_trip(tmp_path):
    path = tmp_path / "phonebook.xml"
    write_xml(path, _CONTACTS)

    result = parse_xml(path)

    assert [c.display_name for c in result.contacts] == ["Max Mustermann", "Erika Musterfrau"]
    max_contact = result.contacts[0]
    assert max_contact.box_uniqueid == "7"
    assert [(n.number_raw, n.number_type) for n in max_contact.numbers] == [
        ("+491234567", "mobile"),
        ("03012345678", "home"),
    ]
    assert result.contacts[1].box_uniqueid is None
    assert result.warnings == []


def test_xml_omits_uniqueid_when_not_box_sourced(tmp_path):
    path = tmp_path / "phonebook.xml"
    write_xml(path, [ImportedContact("Lokal", None, [])])

    assert "<uniqueid>" not in path.read_text()


def test_xml_malformed_raises_import_error(tmp_path):
    path = tmp_path / "bad.xml"
    path.write_text("<not-valid-xml")

    with pytest.raises(PhonebookImportError):
        parse_xml(path)


def test_xml_wrong_root_element_raises_import_error(tmp_path):
    path = tmp_path / "bad.xml"
    path.write_text("<not-a-phonebook/>")

    with pytest.raises(PhonebookImportError):
        parse_xml(path)


def test_xml_contact_without_name_is_skipped_with_warning(tmp_path):
    path = tmp_path / "phonebook.xml"
    path.write_text(
        """<?xml version="1.0"?>
        <phonebooks><phonebook name="x">
        <contact><category>0</category><person><realName></realName></person>
        <telephony nid="1"><number type="home">+491234567</number></telephony></contact>
        </phonebook></phonebooks>"""
    )

    result = parse_xml(path)

    assert result.contacts == []
    assert len(result.warnings) == 1


def test_xml_unparseable_number_is_skipped_with_warning(tmp_path):
    path = tmp_path / "phonebook.xml"
    path.write_text(
        """<?xml version="1.0"?>
        <phonebooks><phonebook name="x">
        <contact><category>0</category><person><realName>Max</realName></person>
        <telephony nid="1"><number type="home">???</number></telephony></contact>
        </phonebook></phonebooks>"""
    )

    result = parse_xml(path)

    assert len(result.contacts) == 1
    assert result.contacts[0].numbers == []
    assert len(result.warnings) == 1


# --- CSV ---


def test_csv_write_then_parse_round_trip(tmp_path):
    path = tmp_path / "phonebook.csv"
    write_csv(path, _CONTACTS)

    result = parse_csv(path)

    assert [c.display_name for c in result.contacts] == ["Max Mustermann", "Erika Musterfrau"]
    assert [n.number_raw for n in result.contacts[0].numbers] == ["+491234567", "03012345678"]
    assert result.contacts[0].notes == "VIP"
    assert result.contacts[1].numbers == []


def test_csv_wrong_header_raises_import_error(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("a,b,c\n1,2,3\n")

    with pytest.raises(PhonebookImportError):
        parse_csv(path)


def test_csv_non_adjacent_rows_sharing_contact_id_group_together(tmp_path):
    path = tmp_path / "phonebook.csv"
    path.write_text(
        "contact_id,display_name,notes,number,number_type\n"
        "1,Max Mustermann,,+491234567,mobile\n"
        "2,Erika Musterfrau,,+499999999,home\n"
        "1,Max Mustermann,,03012345678,home\n"
    )

    result = parse_csv(path)

    assert len(result.contacts) == 2
    max_contact = next(c for c in result.contacts if c.display_name == "Max Mustermann")
    assert len(max_contact.numbers) == 2


def test_csv_invalid_contact_id_row_is_skipped_with_warning(tmp_path):
    path = tmp_path / "phonebook.csv"
    path.write_text(
        "contact_id,display_name,notes,number,number_type\n"
        "abc,Max Mustermann,,+491234567,mobile\n"
    )

    result = parse_csv(path)

    assert result.contacts == []
    assert len(result.warnings) == 1


def test_csv_contact_without_name_is_skipped_with_warning(tmp_path):
    path = tmp_path / "phonebook.csv"
    path.write_text("contact_id,display_name,notes,number,number_type\n1,,,+491234567,mobile\n")

    result = parse_csv(path)

    assert result.contacts == []
    assert len(result.warnings) == 1


def test_csv_cp1252_encoded_native_file_is_parsed(tmp_path):
    path = tmp_path / "phonebook.csv"
    text = "contact_id,display_name,notes,number,number_type\n1,Jürgen Müller,,+491234567,mobile\n"
    path.write_bytes(text.encode("cp1252"))

    result = parse_csv(path)

    assert [c.display_name for c in result.contacts] == ["Jürgen Müller"]


def test_csv_utf8_bom_is_stripped(tmp_path):
    path = tmp_path / "phonebook.csv"
    text = "contact_id,display_name,notes,number,number_type\n1,Max Mustermann,,+491234567,mobile\n"
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))

    result = parse_csv(path)

    assert [c.display_name for c in result.contacts] == ["Max Mustermann"]


def test_csv_unrecognized_header_still_raises_import_error(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("a,b,c\n1,2,3\n")

    with pytest.raises(PhonebookImportError):
        parse_csv(path)


# --- CSV: Adressbuch-Export (Drittanbieter) ---

_THIRDPARTY_CSV_HEADER_LINE = (
    "Private;Last Name;First Name;Company;Street;ZIP Code;City;E-Mail;Picture;"
    "Home;Mobile;Homezone;Business;Other;Fax;Sip;Main\n"
)


def test_csv_thirdparty_schema_parses_multiple_numbers_per_row(tmp_path):
    path = tmp_path / "contacts.csv"
    path.write_text(
        _THIRDPARTY_CSV_HEADER_LINE
        + 'NO;Mustermann;Max;;;;;;;"+491234567";;;"+493012345678";;"+494912345";;\n'
    )

    result = parse_csv(path)

    assert len(result.contacts) == 1
    contact = result.contacts[0]
    assert contact.display_name == "Max Mustermann"
    assert [(n.number_raw, n.number_type) for n in contact.numbers] == [
        ("+491234567", "home"),
        ("+493012345678", "work"),
        ("+494912345", "fax_work"),
    ]


def test_csv_thirdparty_schema_uses_company_when_no_personal_name(tmp_path):
    path = tmp_path / "contacts.csv"
    path.write_text(
        _THIRDPARTY_CSV_HEADER_LINE + 'NO;;;"Acme GmbH";;;;;;"+491234567";;;;;;;\n'
    )

    result = parse_csv(path)

    assert [c.display_name for c in result.contacts] == ["Acme GmbH"]


def test_csv_thirdparty_schema_unnamed_row_uses_first_number_as_name(tmp_path):
    path = tmp_path / "contacts.csv"
    path.write_text(_THIRDPARTY_CSV_HEADER_LINE + 'NO;;;;;;;;;;"+491234567";;;;;;\n')

    result = parse_csv(path)

    assert len(result.contacts) == 1
    contact = result.contacts[0]
    assert contact.display_name == "+491234567"
    assert [n.number_raw for n in contact.numbers] == ["+491234567"]
    assert result.warnings == []


def test_csv_thirdparty_schema_row_without_name_or_number_is_skipped_with_warning(tmp_path):
    path = tmp_path / "contacts.csv"
    path.write_text(_THIRDPARTY_CSV_HEADER_LINE + ";;;;;;;;;;;;;;;;\n")

    result = parse_csv(path)

    assert result.contacts == []
    assert len(result.warnings) == 1


def test_csv_thirdparty_schema_unparseable_number_is_skipped_with_warning(tmp_path):
    path = tmp_path / "contacts.csv"
    path.write_text(_THIRDPARTY_CSV_HEADER_LINE + 'NO;Mustermann;Max;;;;;;;"???";;;;;;;\n')

    result = parse_csv(path)

    assert len(result.contacts) == 1
    assert result.contacts[0].numbers == []
    assert len(result.warnings) == 1


# --- vCard ---


def test_vcard_write_then_parse_round_trip(tmp_path):
    path = tmp_path / "phonebook.vcf"
    write_vcard(path, _CONTACTS)

    result = parse_vcard(path)

    assert [c.display_name for c in result.contacts] == ["Max Mustermann", "Erika Musterfrau"]
    max_contact = result.contacts[0]
    assert max_contact.notes == "VIP"
    assert [(n.number_raw, n.number_type) for n in max_contact.numbers] == [
        ("+491234567", "mobile"),
        ("03012345678", "home"),
    ]


def test_vcard_without_begin_marker_raises_import_error(tmp_path):
    path = tmp_path / "bad.vcf"
    path.write_text("FN:Max Mustermann\n")

    with pytest.raises(PhonebookImportError):
        parse_vcard(path)


def test_vcard_without_fn_is_skipped_with_warning(tmp_path):
    path = tmp_path / "phonebook.vcf"
    path.write_text("BEGIN:VCARD\nVERSION:3.0\nTEL;TYPE=HOME:+491234567\nEND:VCARD\n")

    result = parse_vcard(path)

    assert result.contacts == []
    assert len(result.warnings) == 1


def test_vcard_cp1252_encoded_file_is_parsed(tmp_path):
    path = tmp_path / "phonebook.vcf"
    text = (
        "BEGIN:VCARD\r\nVERSION:3.0\r\n"
        "N;CHARSET=ISO-8859-1:Müller;Jürgen;;\r\n"
        "FN;CHARSET=ISO-8859-1:Jürgen Müller\r\n"
        "TEL;TYPE=cell:+491234567\r\n"
        "END:VCARD\r\n"
    )
    path.write_bytes(text.encode("cp1252"))

    result = parse_vcard(path)

    assert [c.display_name for c in result.contacts] == ["Jürgen Müller"]
    assert result.contacts[0].numbers[0].number_type == "mobile"


# --- import_contacts idempotency ---


def test_import_contacts_creates_new_contacts(connection):
    repo = LocalPhonebookRepository(connection)
    result = ImportResult(contacts=_CONTACTS, warnings=["a warning"])

    summary = import_contacts(repo, result)

    assert summary.created == 2
    assert summary.skipped_duplicate == 0
    assert summary.warnings == ["a warning"]
    assert len(repo.list_all()) == 2


def test_import_contacts_is_idempotent_for_contacts_with_numbers(connection):
    # Nur Kontakte mit mindestens einer Nummer haben ein Duplikat-Erkennungs-
    # merkmal (all_numbers_belong_to_one_contact) - hier isoliert mit einem
    # reinen Nummern-Kontakt getestet, um das von der Namens-only-Ausnahme
    # unten sauber zu trennen.
    repo = LocalPhonebookRepository(connection)
    with_numbers_only = ImportResult(contacts=[_CONTACTS[0]])
    import_contacts(repo, with_numbers_only)

    second = import_contacts(repo, with_numbers_only)

    assert second.created == 0
    assert second.skipped_duplicate == 1
    assert len(repo.list_all()) == 1


def test_import_contacts_recreates_name_only_contacts_on_repeated_import(connection):
    # Bekannte Einschränkung: ein namens-only-Kontakt (keine Nummern) hat kein
    # Merkmal, an dem sich ein Duplikat erkennen liesse, und wird bei jedem
    # erneuten Import als neuer Kontakt angelegt - siehe import_contacts()-Docstring.
    repo = LocalPhonebookRepository(connection)
    name_only = ImportResult(contacts=[_CONTACTS[1]])
    import_contacts(repo, name_only)

    second = import_contacts(repo, name_only)

    assert second.created == 1
    assert second.skipped_duplicate == 0
    assert len(repo.list_all()) == 2
