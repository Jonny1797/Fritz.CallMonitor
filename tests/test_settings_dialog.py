from PySide6.QtWidgets import QDialog

from fritz_callhistory.config import Config
from fritz_callhistory.gui.settings_dialog import SettingsDialog


def test_prefills_from_config(qtbot):
    config = Config(sync_interval_minutes=45, show_incoming_call_popup=False, phonebook_ids=[0])
    dialog = SettingsDialog(config)
    qtbot.addWidget(dialog)

    assert dialog._interval_spin.value() == 45
    assert dialog._popup_checkbox.isChecked() is False
    assert dialog._all_phonebooks_checkbox.isChecked() is False


def test_all_phonebooks_checked_when_config_phonebook_ids_empty(qtbot):
    dialog = SettingsDialog(Config(phonebook_ids=[]))
    qtbot.addWidget(dialog)

    assert dialog._all_phonebooks_checkbox.isChecked() is True


def test_save_without_phonebooks_loaded_keeps_base_phonebook_ids(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.settings_dialog.config_module.save")
    dialog = SettingsDialog(Config(phonebook_ids=[1, 2]))
    qtbot.addWidget(dialog)
    dialog._interval_spin.setValue(60)

    updated = dialog.save(Config(phonebook_ids=[1, 2]))

    assert updated.sync_interval_minutes == 60
    assert updated.phonebook_ids == [1, 2]


def test_phonebooks_unavailable_keeps_all_checkbox_enabled_and_prefills_manual_field(
    qtbot, mocker
):
    mocker.patch("fritz_callhistory.gui.settings_dialog.config_module.save")
    dialog = SettingsDialog(Config(phonebook_ids=[1, 2]))
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.set_phonebooks_unavailable("Keine Zugangsdaten hinterlegt")

    assert dialog._all_phonebooks_checkbox.isEnabled() is True
    assert dialog._manual_ids_edit.isVisible() is True
    assert dialog._manual_ids_edit.text() == "1, 2"


def test_toggling_all_phonebooks_disables_manual_field(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.settings_dialog.config_module.save")
    dialog = SettingsDialog(Config(phonebook_ids=[1, 2]))
    qtbot.addWidget(dialog)
    dialog.set_phonebooks_unavailable("Keine Zugangsdaten hinterlegt")

    dialog._all_phonebooks_checkbox.setChecked(True)
    assert dialog._manual_ids_edit.isEnabled() is False

    dialog._all_phonebooks_checkbox.setChecked(False)
    assert dialog._manual_ids_edit.isEnabled() is True


def test_save_after_manual_entry_uses_parsed_ids(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.settings_dialog.config_module.save")
    dialog = SettingsDialog(Config(phonebook_ids=[1, 2]))
    qtbot.addWidget(dialog)
    dialog.set_phonebooks_unavailable("Keine Zugangsdaten hinterlegt")
    dialog._all_phonebooks_checkbox.setChecked(False)
    dialog._manual_ids_edit.setText("0, 3")

    dialog.accept()
    updated = dialog.save(Config(phonebook_ids=[1, 2]))

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert updated.phonebook_ids == [0, 3]


def test_save_after_manual_entry_with_all_checked_produces_empty_sentinel(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.settings_dialog.config_module.save")
    dialog = SettingsDialog(Config(phonebook_ids=[1, 2]))
    qtbot.addWidget(dialog)
    dialog.set_phonebooks_unavailable("Keine Zugangsdaten hinterlegt")
    dialog._all_phonebooks_checkbox.setChecked(True)

    dialog.accept()
    updated = dialog.save(Config(phonebook_ids=[1, 2]))

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert updated.phonebook_ids == []


def test_accept_with_invalid_manual_ids_is_rejected_and_shows_error(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.settings_dialog.config_module.save")
    dialog = SettingsDialog(Config(phonebook_ids=[1, 2]))
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.set_phonebooks_unavailable("Keine Zugangsdaten hinterlegt")
    dialog._all_phonebooks_checkbox.setChecked(False)
    dialog._manual_ids_edit.setText("abc")

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._manual_ids_error_label.isVisible() is True

    dialog._manual_ids_edit.setText("5")
    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog._manual_ids_error_label.isVisible() is False


def test_accept_with_empty_manual_ids_and_all_unchecked_is_rejected(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.settings_dialog.config_module.save")
    dialog = SettingsDialog(Config(phonebook_ids=[]))
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.set_phonebooks_unavailable("Keine Zugangsdaten hinterlegt")
    dialog._all_phonebooks_checkbox.setChecked(False)
    dialog._manual_ids_edit.setText("")

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._manual_ids_error_label.isVisible() is True


def test_save_with_phonebooks_loaded_uses_checked_ids(qtbot, mocker):
    mock_config_save = mocker.patch("fritz_callhistory.gui.settings_dialog.config_module.save")
    dialog = SettingsDialog(Config(phonebook_ids=[2]))
    qtbot.addWidget(dialog)
    dialog._all_phonebooks_checkbox.setChecked(False)

    dialog.set_phonebooks([(0, "Telefonbuch"), (2, "Extern")])

    assert [(pid, cb.isChecked()) for pid, cb in dialog._phonebook_checkboxes] == [
        (0, False),
        (2, True),
    ]

    dialog._phonebook_checkboxes[0][1].setChecked(True)
    updated = dialog.save(Config())

    assert sorted(updated.phonebook_ids) == [0, 2]
    mock_config_save.assert_called_once_with(updated)


def test_save_with_all_phonebooks_checked_produces_empty_sentinel(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.settings_dialog.config_module.save")
    dialog = SettingsDialog(Config(phonebook_ids=[2]))
    qtbot.addWidget(dialog)
    dialog.set_phonebooks([(0, "Telefonbuch"), (2, "Extern")])
    dialog._all_phonebooks_checkbox.setChecked(True)

    updated = dialog.save(Config())

    assert updated.phonebook_ids == []
