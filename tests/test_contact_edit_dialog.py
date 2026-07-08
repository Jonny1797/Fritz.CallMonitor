from fritz_callhistory.db.repository import LocalPhonebookContact, PhonebookNumber
from fritz_callhistory.gui.contact_edit_dialog import ContactEditDialog


def test_number_type_dropdown_shows_german_labels(qtbot):
    dialog = ContactEditDialog()
    qtbot.addWidget(dialog)

    type_combo = dialog._number_rows[0][2]
    labels = [type_combo.itemText(i) for i in range(type_combo.count())]

    assert labels == ["Privat", "Mobil", "Geschäftlich", "Fax (geschäftlich)", "Sonstige"]


def test_contact_data_returns_internal_english_key_despite_german_label(qtbot):
    dialog = ContactEditDialog()
    qtbot.addWidget(dialog)

    dialog._name_edit.setText("Max Mustermann")
    _container, number_edit, type_combo, _radio = dialog._number_rows[0]
    number_edit.setText("+491234567")
    type_combo.setCurrentIndex(type_combo.findData("mobile"))

    _name, _notes, numbers = dialog.contact_data()

    assert numbers == [("+491234567", "+491234567", "mobile", False)]


def test_editing_existing_contact_preselects_correct_type(qtbot):
    existing = LocalPhonebookContact(
        id=1,
        display_name="Max Mustermann",
        notes=None,
        box_uniqueid=None,
        numbers=[
            PhonebookNumber(
                id=1,
                number_raw="+491234567",
                number_normalized="+491234567",
                number_type="work",
                is_default=False,
            )
        ],
    )
    dialog = ContactEditDialog(existing=existing)
    qtbot.addWidget(dialog)

    type_combo = dialog._number_rows[0][2]

    assert type_combo.currentData() == "work"
    assert type_combo.currentText() == "Geschäftlich"


def test_single_number_row_hides_default_radio(qtbot):
    dialog = ContactEditDialog()
    qtbot.addWidget(dialog)

    radio = dialog._number_rows[0][3]

    assert radio.isHidden() is True
    assert radio.isChecked() is False


def test_second_number_row_shows_default_radios_for_both_rows(qtbot):
    dialog = ContactEditDialog()
    qtbot.addWidget(dialog)

    dialog._add_number_row()

    assert all(not row[3].isHidden() for row in dialog._number_rows)


def test_checking_one_default_radio_unchecks_the_other(qtbot):
    dialog = ContactEditDialog()
    qtbot.addWidget(dialog)
    dialog._add_number_row()

    dialog._number_rows[0][3].setChecked(True)
    dialog._number_rows[1][3].setChecked(True)

    assert dialog._number_rows[0][3].isChecked() is False
    assert dialog._number_rows[1][3].isChecked() is True


def test_contact_data_reports_is_default_for_checked_row_only(qtbot):
    dialog = ContactEditDialog()
    qtbot.addWidget(dialog)
    dialog._add_number_row()

    dialog._name_edit.setText("Max Mustermann")
    dialog._number_rows[0][1].setText("+491234567")
    dialog._number_rows[1][1].setText("+499876543")
    dialog._number_rows[1][3].setChecked(True)

    _name, _notes, numbers = dialog.contact_data()

    assert [n[3] for n in numbers] == [False, True]


def test_contact_data_reports_no_default_when_none_checked(qtbot):
    dialog = ContactEditDialog()
    qtbot.addWidget(dialog)
    dialog._add_number_row()

    dialog._name_edit.setText("Max Mustermann")
    dialog._number_rows[0][1].setText("+491234567")
    dialog._number_rows[1][1].setText("+499876543")

    _name, _notes, numbers = dialog.contact_data()

    assert [n[3] for n in numbers] == [False, False]


def test_editing_existing_contact_preselects_stored_default_radio(qtbot):
    existing = LocalPhonebookContact(
        id=1,
        display_name="Max Mustermann",
        notes=None,
        box_uniqueid=None,
        numbers=[
            PhonebookNumber(
                id=1,
                number_raw="+491234567",
                number_normalized="+491234567",
                number_type="home",
                is_default=False,
            ),
            PhonebookNumber(
                id=2,
                number_raw="+499876543",
                number_normalized="+499876543",
                number_type="mobile",
                is_default=True,
            ),
        ],
    )
    dialog = ContactEditDialog(existing=existing)
    qtbot.addWidget(dialog)

    assert dialog._number_rows[0][3].isChecked() is False
    assert dialog._number_rows[1][3].isChecked() is True


def test_removing_default_row_leaves_no_default_in_remaining_rows(qtbot):
    existing = LocalPhonebookContact(
        id=1,
        display_name="Max Mustermann",
        notes=None,
        box_uniqueid=None,
        numbers=[
            PhonebookNumber(
                id=1,
                number_raw="+491234567",
                number_normalized="+491234567",
                number_type="home",
                is_default=True,
            ),
            PhonebookNumber(
                id=2,
                number_raw="+499876543",
                number_normalized="+499876543",
                number_type="mobile",
                is_default=False,
            ),
        ],
    )
    dialog = ContactEditDialog(existing=existing)
    qtbot.addWidget(dialog)

    dialog._remove_number_row(dialog._number_rows[0][0])

    _name, _notes, numbers = dialog.contact_data()
    assert [n[3] for n in numbers] == [False]
