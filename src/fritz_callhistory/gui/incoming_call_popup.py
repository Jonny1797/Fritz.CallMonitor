"""Immer-im-Vordergrund-Fenster für eingehende Anrufe, ergänzend zum
Tray-Toast in gui/main_window.py's _on_ring() (der von manchen Fensterman-
agern/Betriebssystemen unterdrückt oder zu schnell wieder ausgeblendet
wird). Zeigt Name/Nummer/Notizen und bietet optional eine
"Kontakt anzeigen"-Aktion; Lebenszyklus (wann geschlossen wird) steuert
main_window.py komplett von aussen über CONNECT/DISCONNECT."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class IncomingCallPopup(QWidget):
    open_contact_requested = Signal(int)  # contact_id

    def __init__(
        self,
        connection_id: str,
        title: str,
        subtitle: str,
        notes: str | None,
        contact_id: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Eingehender Anruf")

        self.connection_id = connection_id

        title_label = QLabel(title)
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 2)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            layout.addWidget(subtitle_label)

        if notes:
            notes_label = QLabel(notes)
            notes_label.setWordWrap(True)
            layout.addWidget(notes_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        if contact_id is not None:
            show_contact_button = QPushButton("Kontakt anzeigen")
            show_contact_button.clicked.connect(
                lambda: self._on_open_contact_clicked(contact_id)
            )
            button_row.addWidget(show_contact_button)
        close_button = QPushButton("Schließen")
        close_button.clicked.connect(self.close)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    def _on_open_contact_clicked(self, contact_id: int) -> None:
        self.open_contact_requested.emit(contact_id)
        self.close()
