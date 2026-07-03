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
    _container, number_edit, type_combo = dialog._number_rows[0]
    number_edit.setText("+491234567")
    type_combo.setCurrentIndex(type_combo.findData("mobile"))

    _name, _notes, numbers = dialog.contact_data()

    assert numbers == [("+491234567", "+491234567", "mobile")]


def test_editing_existing_contact_preselects_correct_type(qtbot):
    existing = LocalPhonebookContact(
        id=1,
        display_name="Max Mustermann",
        notes=None,
        box_uniqueid=None,
        numbers=[
            PhonebookNumber(id=1, number_raw="+491234567", number_normalized="+491234567", number_type="work")
        ],
    )
    dialog = ContactEditDialog(existing=existing)
    qtbot.addWidget(dialog)

    type_combo = dialog._number_rows[0][2]

    assert type_combo.currentData() == "work"
    assert type_combo.currentText() == "Geschäftlich"
