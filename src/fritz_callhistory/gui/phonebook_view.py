"""Lokales, editierbares Telefonbuch ("Telefonbuch"-Tab).

Getrennt von der Kontakte-Ansicht (anrufbasiert, ein Kontakt pro Nummer,
automatisch befuellt) - dies hier ist die vom Nutzer gepflegte Quelle der
Wahrheit mit Mehrfachnummern pro Kontakt, Datei-Import/-Export und optionalem
einmaligen Import aus dem Box-Telefonbuch (siehe fritz/client.py's
phonebook_contacts_detailed() - ein automatischer Push zur Box ist ueber
TR-064 nicht moeglich, siehe CLAUDE.md/Planungsnotizen).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.db.repository import (
    ContactRepository,
    LocalPhonebookRepository,
    PhonebookRepository,
)
from fritz_callhistory.gui.contact_edit_dialog import ContactEditDialog
from fritz_callhistory.gui.models import PhonebookContactListModel
from fritz_callhistory.gui.workers import ImportFromBoxFn, ImportFromBoxWorker
from fritz_callhistory.sync.phonebook_io import (
    ImportedContact,
    ImportedNumber,
    PhonebookImportError,
    import_contacts,
    parse_csv,
    parse_vcard,
    parse_xml,
    write_csv,
    write_vcard,
    write_xml,
)
from fritz_callhistory.sync.normalize import normalize_number
from fritz_callhistory.sync.service import resolve_contact_names

_IMPORT_FILTER = "Fritz!Box-Telefonbuch (*.xml);;CSV (*.csv);;vCard (*.vcf)"
_EXPORT_FILTER = "Fritz!Box-Telefonbuch (*.xml);;CSV (*.csv);;vCard (*.vcf)"
_PARSERS = {".xml": parse_xml, ".csv": parse_csv, ".vcf": parse_vcard}
_WRITERS = {".xml": write_xml, ".csv": write_csv, ".vcf": write_vcard}


class PhonebookTab(QWidget):
    contacts_changed = Signal()

    def __init__(
        self,
        connection: sqlite3.Connection,
        import_from_box_fn: ImportFromBoxFn | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._connection = connection
        self._repo = LocalPhonebookRepository(connection)
        self._contacts_repo = ContactRepository(connection)
        self._phonebook_repo = PhonebookRepository(connection)
        self._import_from_box_fn = import_from_box_fn
        self._import_thread: ImportFromBoxWorker | None = None

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Suche nach Name …")
        self._search_edit.textChanged.connect(self._reload)

        self._add_button = QPushButton("Neu")
        self._edit_button = QPushButton("Bearbeiten")
        self._delete_button = QPushButton("Löschen")
        self._import_button = QPushButton("Importieren …")
        self._export_button = QPushButton("Exportieren …")
        self._import_from_box_button = QPushButton("Von Box importieren …")
        self._add_button.clicked.connect(self._on_add_clicked)
        self._edit_button.clicked.connect(self._on_edit_clicked)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        self._import_button.clicked.connect(self._on_import_clicked)
        self._export_button.clicked.connect(self._on_export_clicked)
        self._import_from_box_button.clicked.connect(self._on_import_from_box_clicked)
        self._import_from_box_button.setEnabled(self._import_from_box_fn is not None)

        button_row = QHBoxLayout()
        button_row.addWidget(self._add_button)
        button_row.addWidget(self._edit_button)
        button_row.addWidget(self._delete_button)
        button_row.addStretch()
        button_row.addWidget(self._import_button)
        button_row.addWidget(self._export_button)
        button_row.addWidget(self._import_from_box_button)

        self._model = PhonebookContactListModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(lambda _index: self._on_edit_clicked())

        layout = QVBoxLayout(self)
        layout.addWidget(self._search_edit)
        layout.addLayout(button_row)
        layout.addWidget(self._table)

        self._reload()

    def _reload(self) -> None:
        self._model.set_contacts(self._repo.list_all(self._search_edit.text()))

    def _selected_contact_id(self) -> int | None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self._model.contact_at(indexes[0].row()).id

    def _after_local_change(self) -> None:
        self._reload()
        updated = resolve_contact_names(self._contacts_repo, self._phonebook_repo, self._repo)
        if updated:
            self.contacts_changed.emit()

    def _on_add_clicked(self) -> None:
        dialog = ContactEditDialog(parent=self)
        if dialog.exec() != ContactEditDialog.DialogCode.Accepted:
            return
        name, notes, numbers = dialog.contact_data()
        self._repo.create(display_name=name, notes=notes, numbers=numbers)
        self._after_local_change()

    def _on_edit_clicked(self) -> None:
        contact_id = self._selected_contact_id()
        if contact_id is None:
            return
        existing = self._repo.get(contact_id)
        dialog = ContactEditDialog(existing=existing, parent=self)
        if dialog.exec() != ContactEditDialog.DialogCode.Accepted:
            return
        name, notes, numbers = dialog.contact_data()
        self._repo.update(contact_id, display_name=name, notes=notes, numbers=numbers)
        self._after_local_change()

    def add_or_edit_number(self, number_raw: str) -> None:
        """Einstiegspunkt fuer Doppelklick auf eine Rufnummer in der Kontakte-
        oder Alle-Anrufe-Ansicht (main_window.py): oeffnet den Bearbeiten-Dialog
        fuer den Kontakt, dem diese Nummer bereits gehoert, oder sonst den
        Neu-Dialog mit vorausgefuellter Nummer."""
        normalized, is_anonymous = normalize_number(number_raw)
        if is_anonymous:
            return
        existing = self._repo.find_by_number(normalized)
        dialog = ContactEditDialog(
            existing=existing,
            prefill_number=None if existing else number_raw,
            parent=self,
        )
        if dialog.exec() != ContactEditDialog.DialogCode.Accepted:
            return
        name, notes, numbers = dialog.contact_data()
        if existing:
            self._repo.update(existing.id, display_name=name, notes=notes, numbers=numbers)
        else:
            self._repo.create(display_name=name, notes=notes, numbers=numbers)
        self._after_local_change()

    def _on_delete_clicked(self) -> None:
        contact_id = self._selected_contact_id()
        if contact_id is None:
            return
        contact = self._repo.get(contact_id)
        answer = QMessageBox.question(
            self, "Kontakt löschen", f"'{contact.display_name}' wirklich löschen?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._repo.delete(contact_id)
        self._reload()

    def _on_import_clicked(self) -> None:
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

        summary = import_contacts(self._repo, result)
        message = (
            f"{summary.created} Kontakt(e) importiert, "
            f"{summary.skipped_duplicate} bereits vorhanden übersprungen."
        )
        if summary.warnings:
            message += "\n\nHinweise:\n" + "\n".join(summary.warnings)
        QMessageBox.information(self, "Import abgeschlossen", message)
        self._after_local_change()

    def _on_export_clicked(self) -> None:
        path_str, selected_filter = QFileDialog.getSaveFileName(
            self, "Telefonbuch exportieren", "", _EXPORT_FILTER
        )
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() not in _WRITERS:
            # Endung aus dem gewaehlten Filter ableiten, falls der Nutzer keine angegeben hat.
            suffix = next((s for s in _WRITERS if s.lstrip(".") in selected_filter), ".xml")
            path = path.with_suffix(suffix)
        writer = _WRITERS[path.suffix.lower()]

        contacts = [
            ImportedContact(
                display_name=c.display_name,
                notes=c.notes,
                numbers=[
                    ImportedNumber(n.number_raw, n.number_normalized, n.number_type) for n in c.numbers
                ],
                box_uniqueid=c.box_uniqueid,
            )
            for c in self._repo.list_all()
        ]
        writer(path, contacts)
        QMessageBox.information(self, "Export abgeschlossen", f"{len(contacts)} Kontakt(e) exportiert.")

    def _on_import_from_box_clicked(self) -> None:
        if self._import_from_box_fn is None or (
            self._import_thread is not None and self._import_thread.isRunning()
        ):
            return
        answer = QMessageBox.question(
            self,
            "Von Box importieren",
            "Kontakte aus dem Fritz!Box-Telefonbuch werden importiert bzw. mit bereits "
            "importierten Kontakten abgeglichen (per eindeutiger Box-Id). Rein lokal "
            "angelegte Kontakte werden nur dann automatisch verknüpft, wenn ihre "
            "Rufnummern exakt mit einem Box-Eintrag übereinstimmen - andernfalls können "
            "Duplikate entstehen. Fortfahren?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._import_from_box_button.setEnabled(False)
        self._import_thread = ImportFromBoxWorker(self._import_from_box_fn, parent=self)
        self._import_thread.finished_import.connect(self._on_import_from_box_finished)
        self._import_thread.import_failed.connect(self._on_import_from_box_failed)
        self._import_thread.start()

    def _on_import_from_box_finished(self, imported: int) -> None:
        self._import_from_box_button.setEnabled(self._import_from_box_fn is not None)
        QMessageBox.information(
            self, "Import abgeschlossen", f"{imported} Kontakt(e) von der Box importiert/aktualisiert."
        )
        self._after_local_change()

    def _on_import_from_box_failed(self, message: str) -> None:
        self._import_from_box_button.setEnabled(self._import_from_box_fn is not None)
        QMessageBox.critical(self, "Import fehlgeschlagen", message)
