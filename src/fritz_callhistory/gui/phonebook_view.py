"""Lokales, editierbares Telefonbuch ("Telefonbuch"-Tab).

Getrennt von der Kontakte-Ansicht (anrufbasiert, ein Kontakt pro Nummer,
automatisch befüllt) - dies hier ist die vom Nutzer gepflegte Quelle der
Wahrheit mit Mehrfachnummern pro Kontakt, Datei-Import/-Export und optionalem
einmaligen Import aus dem Box-Telefonbuch (siehe fritz/client.py's
phonebook_contacts_detailed() - ein automatischer Push zur Box ist über
TR-064 nicht möglich, siehe CLAUDE.md/Planungsnotizen).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.gui.contact_edit_dialog import ContactEditDialog
from fritz_callhistory.gui.models import (
    PHONEBOOK_COLUMNS,
    configure_table,
    DataclassSortProxy,
    PhonebookContactListModel,
    default_or_first_number,
    focus_search_edit,
    install_phonebook_call_context_menu,
    selected_source_row,
)
from fritz_callhistory.fritz.exceptions import FritzBoxError
from fritz_callhistory.gui.background_tasks import BackgroundTasks
from fritz_callhistory.sync.box_gateway import BoxGateway
from fritz_callhistory.sync.phonebook_io import (
    PhonebookImportError,
    parse_csv,
    parse_vcard,
    parse_xml,
    write_csv,
    write_vcard,
    write_xml,
)
from fritz_callhistory.sync.caller_directory import CallerDirectory
from fritz_callhistory.sync.normalize import normalize_number
from fritz_callhistory.sync.telefonbuch import Telefonbuch

_IMPORT_FILTER = "Fritz!Box-Telefonbuch (*.xml);;CSV (*.csv);;vCard (*.vcf)"
_EXPORT_FILTER = "Fritz!Box-Telefonbuch (*.xml);;CSV (*.csv);;vCard (*.vcf)"
_PARSERS = {".xml": parse_xml, ".csv": parse_csv, ".vcf": parse_vcard}
_WRITERS = {".xml": write_xml, ".csv": write_csv, ".vcf": write_vcard}


_IMPORT_KEY = "box-import"


class PhonebookTab(QWidget):
    contacts_changed = Signal()
    call_requested = Signal(str)
    import_from_box_availability_changed = Signal(bool)

    def __init__(
        self,
        connection: sqlite3.Connection,
        background_tasks: BackgroundTasks,
        gateway: BoxGateway,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._connection = connection
        self._telefonbuch = Telefonbuch(connection)
        self._gateway = gateway
        self._background_tasks = background_tasks

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Suche nach Name …")
        self._search_edit.textChanged.connect(self._reload)

        self._add_button = QPushButton("Neu")
        self._edit_button = QPushButton("Bearbeiten")
        self._delete_button = QPushButton("Löschen")
        self._add_button.clicked.connect(self._on_add_clicked)
        self._edit_button.clicked.connect(self._on_edit_clicked)
        self._delete_button.clicked.connect(self._on_delete_clicked)

        button_row = QHBoxLayout()
        button_row.addWidget(self._add_button)
        button_row.addWidget(self._edit_button)
        button_row.addWidget(self._delete_button)
        button_row.addStretch()

        self._model = PhonebookContactListModel()
        self._proxy = DataclassSortProxy(
            row_getter=self._model.contact_at,
            columns=PHONEBOOK_COLUMNS,
        )
        self._proxy.setSourceModel(self._model)

        self._table = QTableView()
        configure_table(self._table, self._proxy)
        self._table.doubleClicked.connect(lambda _index: self._on_edit_clicked())
        install_phonebook_call_context_menu(
            self._table, self._proxy, self._model.contact_at, self.call_requested.emit
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self._search_edit)
        layout.addLayout(button_row)
        layout.addWidget(self._table)

        self._reload()

    @property
    def can_import_from_box(self) -> bool:
        return self._gateway.has_credentials and not self._background_tasks.is_running(_IMPORT_KEY)

    def _reload(self) -> None:
        self._model.set_contacts(self._telefonbuch.list(self._search_edit.text()))

    def _selected_contact_id(self) -> int | None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        source_row = self._proxy.mapToSource(indexes[0]).row()
        return self._model.contact_at(source_row).id

    def focus_search(self) -> None:
        focus_search_edit(self._search_edit)

    def dial_selected(self) -> None:
        row = selected_source_row(self._table, self._proxy)
        if row is None:
            return
        number = default_or_first_number(self._model.contact_at(row))
        if number is not None:
            self.call_requested.emit(number)

    def _after_local_change(self) -> None:
        self._reload()
        directory = CallerDirectory.for_connection(self._connection)
        updated = directory.refresh_names()
        if updated:
            self.contacts_changed.emit()

    def _on_add_clicked(self) -> None:
        dialog = ContactEditDialog(parent=self)
        if dialog.exec() != ContactEditDialog.DialogCode.Accepted:
            return
        self._telefonbuch.create(dialog.contact_draft())
        self._after_local_change()

    def _on_edit_clicked(self) -> None:
        contact_id = self._selected_contact_id()
        if contact_id is None:
            return
        existing = self._telefonbuch.get(contact_id)
        dialog = ContactEditDialog(existing=existing, parent=self)
        if dialog.exec() != ContactEditDialog.DialogCode.Accepted:
            return
        self._telefonbuch.update(contact_id, dialog.contact_draft())
        self._after_local_change()

    def add_or_edit_number(self, number_raw: str) -> None:
        """Einstiegspunkt für Doppelklick auf eine Rufnummer in der Kontakte-
        oder Alle-Anrufe-Ansicht (main_window.py): öffnet den Bearbeiten-Dialog
        für den Kontakt, dem diese Nummer bereits gehört, oder sonst den
        Neu-Dialog mit vorausgefüllter Nummer."""
        if normalize_number(number_raw)[1]:
            return
        existing = self._telefonbuch.find_by_number(number_raw)
        dialog = ContactEditDialog(
            existing=existing,
            prefill_number=None if existing else number_raw,
            parent=self,
        )
        if dialog.exec() != ContactEditDialog.DialogCode.Accepted:
            return
        if existing:
            self._telefonbuch.update(existing.id, dialog.contact_draft())
        else:
            self._telefonbuch.create(dialog.contact_draft())
        self._after_local_change()

    def _on_delete_clicked(self) -> None:
        contact_id = self._selected_contact_id()
        if contact_id is None:
            return
        contact = self._telefonbuch.get(contact_id)
        answer = QMessageBox.question(
            self, "Kontakt löschen", f"'{contact.display_name}' wirklich löschen?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._telefonbuch.delete(contact_id)
        self._after_local_change()

    def import_from_file(self) -> None:
        path_str, _selected_filter = QFileDialog.getOpenFileName(
            self, "Telefonbuch importieren", "", _IMPORT_FILTER
        )
        if not path_str:
            return
        path = Path(path_str)
        parser = _PARSERS.get(path.suffix.lower())
        if parser is None:
            QMessageBox.critical(self, "Import fehlgeschlagen", "Unbekanntes Dateiformat.")
            return
        try:
            result = parser(path)
        except PhonebookImportError as exc:
            QMessageBox.critical(self, "Import fehlgeschlagen", str(exc))
            return

        summary = self._telefonbuch.import_file(result)
        message = (
            f"{summary.created} Kontakt(e) importiert, "
            f"{summary.skipped_duplicate} bereits vorhanden übersprungen."
        )
        if summary.warnings:
            message += "\n\nHinweise:\n" + "\n".join(summary.warnings)
        QMessageBox.information(self, "Import abgeschlossen", message)
        self._after_local_change()

    def export_to_file(self) -> None:
        path_str, selected_filter = QFileDialog.getSaveFileName(
            self, "Telefonbuch exportieren", "", _EXPORT_FILTER
        )
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() not in _WRITERS:
            # Endung aus dem gewählten Filter ableiten, falls der Nutzer keine angegeben hat.
            suffix = next((s for s in _WRITERS if s.lstrip(".") in selected_filter), ".xml")
            path = path.with_suffix(suffix)
        writer = _WRITERS[path.suffix.lower()]

        contacts = self._telefonbuch.all_contacts()
        writer(path, contacts)
        QMessageBox.information(self, "Export abgeschlossen", f"{len(contacts)} Kontakt(e) exportiert.")

    def import_from_box(self, phonebook_ids: list[int]) -> None:
        """*phonebook_ids* kommt aus MainWindow._open_phonebook_import_dialog()'s
        PhonebookPickerDialog - die Auswahl dort dient bereits als Bestätigung,
        daher kein zusätzlicher QMessageBox.question() mehr hier."""
        if not self._gateway.has_credentials or self._background_tasks.is_running(_IMPORT_KEY):
            return

        started = self._background_tasks.start(
            lambda: self._gateway.import_from_box(phonebook_ids),
            self,
            self._on_import_from_box_finished,
            self._on_import_from_box_failed,
            key=_IMPORT_KEY,
        )
        if started:
            self.import_from_box_availability_changed.emit(False)

    def _on_import_from_box_finished(self, imported: object) -> None:
        self.import_from_box_availability_changed.emit(self.can_import_from_box)
        QMessageBox.information(
            self, "Import abgeschlossen", f"{imported} Kontakt(e) von der Box importiert/aktualisiert."
        )
        self._after_local_change()

    def _on_import_from_box_failed(self, error: FritzBoxError) -> None:
        self.import_from_box_availability_changed.emit(self.can_import_from_box)
        QMessageBox.critical(self, "Import fehlgeschlagen", str(error))
