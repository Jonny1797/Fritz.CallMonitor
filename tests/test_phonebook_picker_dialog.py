from PySide6.QtWidgets import QDialog

from fritz_callhistory.gui.phonebook_picker_dialog import PhonebookPickerDialog


def test_ok_disabled_until_phonebooks_arrive(qtbot):
    dialog = PhonebookPickerDialog()
    qtbot.addWidget(dialog)

    assert dialog._ok_button.isEnabled() is False


def test_set_phonebooks_checks_all_by_default_and_enables_ok(qtbot):
    dialog = PhonebookPickerDialog()
    qtbot.addWidget(dialog)

    dialog.set_phonebooks([(0, "Telefonbuch"), (2, "Extern")])

    assert [(pid, cb.isChecked()) for pid, cb in dialog._phonebook_checkboxes] == [
        (0, True),
        (2, True),
    ]
    assert dialog._ok_button.isEnabled() is True
    assert dialog.selected_phonebook_ids() == [0, 2]


def test_unchecking_a_phonebook_excludes_it_from_selection(qtbot):
    dialog = PhonebookPickerDialog()
    qtbot.addWidget(dialog)
    dialog.set_phonebooks([(0, "Telefonbuch"), (2, "Extern")])

    dialog._phonebook_checkboxes[1][1].setChecked(False)

    assert dialog.selected_phonebook_ids() == [0]


def test_set_phonebooks_unavailable_keeps_ok_disabled(qtbot):
    dialog = PhonebookPickerDialog()
    qtbot.addWidget(dialog)

    dialog.set_phonebooks_unavailable("Keine Zugangsdaten hinterlegt")

    assert dialog._ok_button.isEnabled() is False


def test_accept_with_no_phonebooks_checked_is_rejected_and_shows_error(qtbot):
    dialog = PhonebookPickerDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.set_phonebooks([(0, "Telefonbuch")])
    dialog._phonebook_checkboxes[0][1].setChecked(False)

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._error_label.isVisible() is True

    dialog._phonebook_checkboxes[0][1].setChecked(True)
    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog._error_label.isVisible() is False
