"""Anrufbeantworter-Tab: Nachrichtenliste mit einer Aktionsleiste (Abspielen/
Anrufen/Gelesen/Löschen, je nach Auswahl aktiviert) und einer Wiedergabeleiste
mit klickbarer Sucheiste am unteren Rand."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.fritz.exceptions import FritzBoxError
from fritz_callhistory.gui.background_tasks import BackgroundTasks
from fritz_callhistory.sync.box_gateway import BoxGateway
from fritz_callhistory.db.repository import (
    VoicemailMessageRecord,
    VoicemailRepository,
)
from fritz_callhistory.sync.caller_directory import CallerDirectory
from fritz_callhistory.gui.models import (
    configure_table,
    DataclassSortProxy,
    VoicemailListModel,
)

_AUDIO_KEY = "voicemail-audio"
_ACTION_KEY = "voicemail-action"



def _format_ms(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


class _SeekSlider(QSlider):
    """QSlider springt bei einem Klick auf die Leiste standardmäßig nur einen
    Seitenschritt statt an die geklickte Position - überschreibt mousePressEvent,
    um sofort dorthin zu springen (Drag-Verhalten bleibt über super() erhalten)."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.maximum() > self.minimum():
            value = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(event.position().x()), self.width()
            )
            self.setValue(value)
            self.sliderMoved.emit(value)
        super().mousePressEvent(event)


class VoicemailView(QWidget):
    call_requested = Signal(str)
    new_voicemail_count_changed = Signal(int)

    def __init__(
        self,
        connection: sqlite3.Connection,
        background_tasks: BackgroundTasks,
        gateway: BoxGateway,
    ) -> None:
        super().__init__()
        self._voicemail_repo = VoicemailRepository(connection)
        self._caller_directory = CallerDirectory.for_connection(connection)
        self._gateway = gateway
        self._background_tasks = background_tasks
        self._new_voicemail_count = 0
        # Player-Quelle (QByteArray/QBuffer) als Instanzattribute halten, damit sie
        # während der Wiedergabe nicht vom GC eingesammelt werden (QMediaPlayer
        # hält selbst keine Python-Referenz auf sourceDevice()).
        self._audio_bytes: QByteArray | None = None
        self._audio_buffer: QBuffer | None = None

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

        self._model = VoicemailListModel()
        self._proxy = DataclassSortProxy(
            row_getter=self._model.message_at,
            columns=self._model.columns,
        )
        self._proxy.setSourceModel(self._model)

        self._table = QTableView()
        configure_table(self._table, self._proxy)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        self._table.selectionModel().selectionChanged.connect(self._update_action_buttons)

        self._play_button = QPushButton("Abspielen")
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self._on_play_button_clicked)
        self._call_button = QPushButton("Anrufen")
        self._call_button.setEnabled(False)
        self._call_button.clicked.connect(self._on_call_button_clicked)
        self._read_button = QPushButton("Gelesen")
        self._read_button.setEnabled(False)
        self._read_button.clicked.connect(self._on_read_button_clicked)
        self._delete_button = QPushButton("Löschen")
        self._delete_button.setEnabled(False)
        self._delete_button.clicked.connect(self._on_delete_button_clicked)

        action_row = QHBoxLayout()
        action_row.addWidget(self._play_button)
        action_row.addWidget(self._call_button)
        action_row.addWidget(self._read_button)
        action_row.addWidget(self._delete_button)
        action_row.addStretch()

        self._now_playing_label = QLabel()
        self._play_pause_button = QPushButton("▶")
        self._play_pause_button.setEnabled(False)
        self._play_pause_button.clicked.connect(self._on_play_pause_clicked)
        self._position_slider = _SeekSlider(Qt.Orientation.Horizontal)
        self._position_slider.setEnabled(False)
        self._position_slider.sliderMoved.connect(self._player.setPosition)
        self._position_label = QLabel("0:00 / 0:00")

        transport_row = QHBoxLayout()
        transport_row.addWidget(self._play_pause_button)
        transport_row.addWidget(self._position_slider)
        transport_row.addWidget(self._position_label)

        layout = QVBoxLayout(self)
        layout.addLayout(action_row)
        layout.addWidget(self._table)
        layout.addWidget(self._now_playing_label)
        layout.addLayout(transport_row)

        self.reload()

    @property
    def new_voicemail_count(self) -> int:
        return self._new_voicemail_count

    def reload(self) -> None:
        """Lädt die Nachrichtenliste neu (z.B. nach einem Sync oder einer Aktion)."""
        messages = self._voicemail_repo.list_messages()
        # Eine gebatchte Abfrage für alle Nachrichten (rohe Box-Nummern)
        identities = self._caller_directory.identify_many([m.caller_number for m in messages])
        labels = {
            m.id: identities[m.caller_number].label(fallback_name=m.raw_name) for m in messages
        }
        self._model.set_messages(messages, labels)
        self._new_voicemail_count = sum(1 for m in messages if m.is_new)
        self.new_voicemail_count_changed.emit(self._new_voicemail_count)
        self._update_action_buttons()

    def _selected_message(self) -> VoicemailMessageRecord | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._model.message_at(self._proxy.mapToSource(rows[0]).row())

    def dial_selected(self) -> None:
        self._on_call_button_clicked()

    def _update_action_buttons(self) -> None:
        # Während eine Gelesen-/Löschen-Aktion noch läuft, bleiben alle vier
        # Buttons deaktiviert - sonst könnte z.B. eine Löschen-Bestätigung
        # über eine noch laufende Gelesen-Aktion hinweg bestätigt werden und
        # danach durch den geteilten Aufgaben-Schlüssel stillschweigend nichts
        # mehr tun.
        action_running = self._background_tasks.is_running(_ACTION_KEY)
        message = None if action_running else self._selected_message()
        self._play_button.setEnabled(message is not None)
        self._call_button.setEnabled(message is not None and bool(message.caller_number))
        self._read_button.setEnabled(message is not None and message.is_new)
        self._delete_button.setEnabled(message is not None)

    def _on_row_double_clicked(self, index) -> None:
        source_row = self._proxy.mapToSource(index).row()
        self.play_message(self._model.message_at(source_row))

    def _on_play_button_clicked(self) -> None:
        message = self._selected_message()
        if message is not None:
            self.play_message(message)

    def _on_call_button_clicked(self) -> None:
        message = self._selected_message()
        if message is not None and message.caller_number:
            self.call_requested.emit(message.caller_number)

    def _on_read_button_clicked(self) -> None:
        message = self._selected_message()
        if message is not None:
            self._mark_read(message)

    def _on_delete_button_clicked(self) -> None:
        message = self._selected_message()
        if message is None:
            return
        confirmed = QMessageBox.question(
            self,
            "Nachricht löschen",
            f"Nachricht von {self._model.caller_label(message)} wirklich löschen?\n"
            "Dies löscht sie auch auf der Fritz!Box und kann nicht rückgängig "
            "gemacht werden.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed == QMessageBox.StandardButton.Yes:
            self._delete_message(message)

    def play_message(self, message: VoicemailMessageRecord) -> None:
        if not self._gateway.has_credentials or self._background_tasks.is_running(_AUDIO_KEY):
            return
        started = self._background_tasks.start(
            lambda: self._gateway.voicemail_audio(message),
            self,
            lambda data: self._on_audio_ready(message, data),
            self._on_audio_failed,
            key=_AUDIO_KEY,
        )
        if started:
            self._now_playing_label.setText(
                f"Lade Nachricht von {self._model.caller_label(message)} …"
            )

    def _on_audio_ready(self, message: VoicemailMessageRecord, data: bytes) -> None:
        self._now_playing_label.setText(f"Wird abgespielt: {self._model.caller_label(message)}")
        # Playing already marks the message read on the box (see
        # BoxGateway.voicemail_audio) - flip it locally too, right away,
        # so the unread styling clears immediately instead of waiting for the next
        # sync (same as the explicit "Gelesen" button does).
        self._voicemail_repo.mark_read_locally(message.id)
        self.reload()
        self._audio_bytes = QByteArray(data)
        self._audio_buffer = QBuffer(self)
        self._audio_buffer.setData(self._audio_bytes)
        self._audio_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._player.setSourceDevice(self._audio_buffer)
        self._player.play()

    def _on_audio_failed(self, error: FritzBoxError) -> None:
        self._now_playing_label.setText(f"Abspielen fehlgeschlagen: {error}")

    def _mark_read(self, message: VoicemailMessageRecord) -> None:
        if not self._gateway.has_credentials:
            return
        self._run_action(
            lambda: self._gateway.voicemail_mark_read(message),
            lambda: self._on_mark_read_succeeded(message),
        )

    def _on_mark_read_succeeded(self, message: VoicemailMessageRecord) -> None:
        self._voicemail_repo.mark_read_locally(message.id)
        self.reload()

    def _delete_message(self, message: VoicemailMessageRecord) -> None:
        if not self._gateway.has_credentials:
            return
        self._run_action(
            lambda: self._gateway.voicemail_delete(message),
            lambda: self._on_delete_succeeded(message),
        )

    def _on_delete_succeeded(self, message: VoicemailMessageRecord) -> None:
        self._voicemail_repo.delete(message.id)
        self.reload()

    def _run_action(self, fn: Callable[[], None], on_done: Callable[[], None]) -> None:
        """Startet eine Gelesen-/Löschen-Aktion; es läuft immer nur eine."""
        started = self._background_tasks.start(
            fn,
            self,
            lambda _result: on_done(),
            self._on_action_failed,
            key=_ACTION_KEY,
        )
        if started:
            self._update_action_buttons()

    def _on_action_failed(self, error: FritzBoxError) -> None:
        self._now_playing_label.setText(f"Aktion fehlgeschlagen: {error}")
        self._update_action_buttons()

    def _on_play_pause_clicked(self) -> None:
        if self._player.isPlaying():
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_pause_button.setText("⏸" if playing else "▶")
        self._play_pause_button.setEnabled(state != QMediaPlayer.PlaybackState.StoppedState)
        self._position_slider.setEnabled(state != QMediaPlayer.PlaybackState.StoppedState)

    def _on_position_changed(self, position: int) -> None:
        self._position_slider.setValue(position)
        self._position_label.setText(f"{_format_ms(position)} / {_format_ms(self._player.duration())}")

    def _on_duration_changed(self, duration: int) -> None:
        self._position_slider.setRange(0, duration)
