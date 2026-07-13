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
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.db.repository import VoicemailMessageRecord, VoicemailRepository
from fritz_callhistory.gui.models import (
    DataclassSortProxy,
    VoicemailListModel,
    install_tristate_sorting,
    voicemail_caller_display,
)
from fritz_callhistory.gui.workers import VoicemailActionWorker, VoicemailAudioWorker

AudioFetchFn = Callable[[VoicemailMessageRecord], bytes]
VoicemailActionFn = Callable[[VoicemailMessageRecord], None]


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
        audio_fetch_fn: AudioFetchFn | None = None,
        mark_read_fn: VoicemailActionFn | None = None,
        delete_fn: VoicemailActionFn | None = None,
    ) -> None:
        super().__init__()
        self._voicemail_repo = VoicemailRepository(connection)
        self._audio_fetch_fn = audio_fetch_fn
        self._mark_read_fn = mark_read_fn
        self._delete_fn = delete_fn
        self._audio_thread: VoicemailAudioWorker | None = None
        self._action_thread: VoicemailActionWorker | None = None
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
            key_fns={
                0: lambda m: m.message_date,
                1: lambda m: voicemail_caller_display(m).lower(),
                2: lambda m: m.duration_seconds,
            },
        )
        self._proxy.setSourceModel(self._model)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        self._table.selectionModel().selectionChanged.connect(self._update_action_buttons)
        install_tristate_sorting(self._table, self._proxy)

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
    def audio_thread(self) -> VoicemailAudioWorker | None:
        return self._audio_thread

    @property
    def action_thread(self) -> VoicemailActionWorker | None:
        return self._action_thread

    @property
    def new_voicemail_count(self) -> int:
        return self._new_voicemail_count

    def reload(self) -> None:
        """Lädt die Nachrichtenliste neu (z.B. nach einem Sync oder einer Aktion)."""
        messages = self._voicemail_repo.list_messages()
        self._model.set_messages(messages)
        self._new_voicemail_count = sum(1 for m in messages if m.is_new)
        self.new_voicemail_count_changed.emit(self._new_voicemail_count)
        self._update_action_buttons()

    def _selected_message(self) -> VoicemailMessageRecord | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._model.message_at(self._proxy.mapToSource(rows[0]).row())

    def focus_search(self) -> None:
        pass  # kein Suchfeld in diesem Tab - Stub für die einheitliche MainWindow-Dispatch-Schnittstelle

    def dial_selected(self) -> None:
        self._on_call_button_clicked()

    def _update_action_buttons(self) -> None:
        # Während eine Gelesen-/Löschen-Aktion noch läuft, bleiben alle vier
        # Buttons deaktiviert - sonst könnte z.B. eine Löschen-Bestätigung
        # über eine noch laufende Gelesen-Aktion hinweg bestätigt werden und
        # danach durch den geteilten _action_thread-Guard stillschweigend nichts
        # mehr tun.
        message = None if self._action_thread is not None else self._selected_message()
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
            f"Nachricht von {voicemail_caller_display(message)} wirklich löschen?\n"
            "Dies löscht sie auch auf der Fritz!Box und kann nicht rückgängig "
            "gemacht werden.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed == QMessageBox.StandardButton.Yes:
            self._delete_message(message)

    def play_message(self, message: VoicemailMessageRecord) -> None:
        if self._audio_fetch_fn is None or self._audio_thread is not None:
            return
        self._now_playing_label.setText(f"Lade Nachricht von {voicemail_caller_display(message)} …")
        self._audio_thread = VoicemailAudioWorker(
            lambda: self._audio_fetch_fn(message), parent=self
        )
        self._audio_thread.audio_ready.connect(
            lambda data: self._on_audio_ready(message, data)
        )
        self._audio_thread.audio_failed.connect(self._on_audio_failed)
        self._audio_thread.finished.connect(self._on_audio_thread_finished)
        self._audio_thread.start()

    def _on_audio_ready(self, message: VoicemailMessageRecord, data: bytes) -> None:
        self._now_playing_label.setText(f"Wird abgespielt: {voicemail_caller_display(message)}")
        # Playing already marks the message read on the box (see
        # app.py's _build_voicemail_audio_fn) - flip it locally too, right away,
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

    def _on_audio_failed(self, message: str) -> None:
        self._now_playing_label.setText(f"Abspielen fehlgeschlagen: {message}")

    def _on_audio_thread_finished(self) -> None:
        self._audio_thread = None

    def _mark_read(self, message: VoicemailMessageRecord) -> None:
        if self._mark_read_fn is None or self._action_thread is not None:
            return
        self._action_thread = VoicemailActionWorker(
            lambda: self._mark_read_fn(message), parent=self
        )
        self._action_thread.action_succeeded.connect(
            lambda: self._on_mark_read_succeeded(message)
        )
        self._action_thread.action_failed.connect(self._on_action_failed)
        self._action_thread.finished.connect(self._on_action_thread_finished)
        self._action_thread.start()
        self._update_action_buttons()

    def _on_mark_read_succeeded(self, message: VoicemailMessageRecord) -> None:
        self._voicemail_repo.mark_read_locally(message.id)
        self.reload()

    def _delete_message(self, message: VoicemailMessageRecord) -> None:
        if self._delete_fn is None or self._action_thread is not None:
            return
        self._action_thread = VoicemailActionWorker(
            lambda: self._delete_fn(message), parent=self
        )
        self._action_thread.action_succeeded.connect(
            lambda: self._on_delete_succeeded(message)
        )
        self._action_thread.action_failed.connect(self._on_action_failed)
        self._action_thread.finished.connect(self._on_action_thread_finished)
        self._action_thread.start()
        self._update_action_buttons()

    def _on_delete_succeeded(self, message: VoicemailMessageRecord) -> None:
        self._voicemail_repo.delete(message.id)
        self.reload()

    def _on_action_failed(self, message: str) -> None:
        self._now_playing_label.setText(f"Aktion fehlgeschlagen: {message}")

    def _on_action_thread_finished(self) -> None:
        self._action_thread = None
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
