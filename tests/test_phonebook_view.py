from PySide6.QtWidgets import QDialog, QMessageBox

from fritz_callhistory.db.repository import ContactRepository, LocalPhonebookRepository
from fritz_callhistory.gui.contact_edit_dialog import ContactEditDialog
from fritz_callhistory.gui.main_window import MainWindow
from fritz_callhistory.gui.phonebook_view import PhonebookTab


def test_phonebook_tab_shows_seeded_contacts(qtbot, connection):
    repo = LocalPhonebookRepository(connection)
    repo.create(display_name="Max Mustermann", notes=None, numbers=[])

    tab = PhonebookTab(connection)
    qtbot.addWidget(tab)

    assert tab._model.rowCount() == 1
    assert tab._model.contact_at(0).display_name == "Max Mustermann"


def test_phonebook_tab_search_filters_by_name(qtbot, connection):
    repo = LocalPhonebookRepository(connection)
    repo.create(display_name="Max Mustermann", notes=None, numbers=[])
    repo.create(display_name="Erika Musterfrau", notes=None, numbers=[])

    tab = PhonebookTab(connection)
    qtbot.addWidget(tab)

    tab._search_edit.setText("Mustermann")

    assert tab._model.rowCount() == 1
    assert tab._model.contact_at(0).display_name == "Max Mustermann"


def test_import_from_box_button_disabled_without_fn(qtbot, connection):
    tab = PhonebookTab(connection, import_from_box_fn=None)
    qtbot.addWidget(tab)
    assert tab._import_from_box_button.isEnabled() is False


def test_import_from_box_button_enabled_with_fn(qtbot, connection):
    tab = PhonebookTab(connection, import_from_box_fn=lambda: 0)
    qtbot.addWidget(tab)
    assert tab._import_from_box_button.isEnabled() is True


def test_add_contact_via_dialog_persists_and_reloads(qtbot, connection, mocker):
    tab = PhonebookTab(connection)
    qtbot.addWidget(tab)

    def fake_exec(self):
        self._name_edit.setText("Max Mustermann")
        return QDialog.DialogCode.Accepted

    mocker.patch.object(ContactEditDialog, "exec", fake_exec)

    tab._on_add_clicked()

    assert tab._model.rowCount() == 1
    assert tab._model.contact_at(0).display_name == "Max Mustermann"


def test_edit_contact_updates_existing_entry(qtbot, connection, mocker):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(display_name="Max Mustermann", notes=None, numbers=[])

    tab = PhonebookTab(connection)
    qtbot.addWidget(tab)
    tab._table.selectRow(0)

    def fake_exec(self):
        self._name_edit.setText("Max M. Aktualisiert")
        return QDialog.DialogCode.Accepted

    mocker.patch.object(ContactEditDialog, "exec", fake_exec)

    tab._on_edit_clicked()

    assert repo.get(contact_id).display_name == "Max M. Aktualisiert"


def test_delete_contact_removes_it(qtbot, connection, mocker):
    repo = LocalPhonebookRepository(connection)
    repo.create(display_name="Max Mustermann", notes=None, numbers=[])

    tab = PhonebookTab(connection)
    qtbot.addWidget(tab)
    tab._table.selectRow(0)

    mocker.patch(
        "fritz_callhistory.gui.phonebook_view.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )

    tab._on_delete_clicked()

    assert tab._model.rowCount() == 0
    assert repo.list_all() == []


def test_add_or_edit_number_creates_new_contact_with_prefilled_number(qtbot, connection, mocker):
    tab = PhonebookTab(connection)
    qtbot.addWidget(tab)

    captured_prefill = {}

    def fake_exec(self):
        captured_prefill["value"] = self._number_rows[0][1].text()
        self._name_edit.setText("Max Mustermann")
        return QDialog.DialogCode.Accepted

    mocker.patch.object(ContactEditDialog, "exec", fake_exec)

    tab.add_or_edit_number("0171 2345678")

    assert captured_prefill["value"] == "0171 2345678"
    assert tab._model.rowCount() == 1
    assert tab._model.contact_at(0).display_name == "Max Mustermann"


def test_add_or_edit_number_edits_existing_contact_for_matching_number(qtbot, connection, mocker):
    repo = LocalPhonebookRepository(connection)
    contact_id = repo.create(
        display_name="Max Mustermann", notes=None, numbers=[("0171 2345678", "+491712345678", "mobile")]
    )

    tab = PhonebookTab(connection)
    qtbot.addWidget(tab)

    def fake_exec(self):
        assert self._existing is not None and self._existing.id == contact_id
        self._name_edit.setText("Max M. Aktualisiert")
        return QDialog.DialogCode.Accepted

    mocker.patch.object(ContactEditDialog, "exec", fake_exec)

    tab.add_or_edit_number("0171 2345678")

    assert repo.get(contact_id).display_name == "Max M. Aktualisiert"
    assert tab._model.rowCount() == 1


def test_add_or_edit_number_ignores_anonymous_number(qtbot, connection, mocker):
    tab = PhonebookTab(connection)
    qtbot.addWidget(tab)
    exec_spy = mocker.patch.object(ContactEditDialog, "exec")

    tab.add_or_edit_number("")

    exec_spy.assert_not_called()
    assert tab._model.rowCount() == 0


def test_adding_local_contact_renames_matching_call_history_contact(qtbot, connection):
    contacts_repo = ContactRepository(connection)
    contact_id = contacts_repo.upsert("+491234567")

    window = MainWindow(connection)
    qtbot.addWidget(window)

    window._phonebook_tab._repo.create(
        display_name="Neu Erkannt",
        notes=None,
        numbers=[("0171 2345678", "+491234567", "mobile")],
    )
    window._phonebook_tab._after_local_change()

    assert contacts_repo.get(contact_id).display_name == "Neu Erkannt"
