"""Anrufbeantworter-Tab: Nachrichtenliste mit Kontextmenü (Anrufen/Abspielen/
Ausblenden) und einer schlanken Inline-Wiedergabeleiste."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSlider,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.db.repository import VoicemailMessageRecord, VoicemailRepository
from fritz_callhistory.gui.models import (
    DataclassSortProxy,
    VoicemailListModel,
    install_tristate_sorting,
    install_voicemail_context_menu,
    voicemail_caller_display,
)
from fritz_callhistory.gui.workers import VoicemailAudioWorker

AudioFetchFn = Callable[[VoicemailMessageRecord], bytes]


def _format_ms(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


class VoicemailView(QWidget):
    call_requested = Signal(str)
    new_voicemail_count_changed = Signal(int)

    def __init__(
        self,
        connection: sqlite3.Connection,
        audio_fetch_fn: AudioFetchFn | None = None,
    ) -> None:
        super().__init__()
        self._voicemail_repo = VoicemailRepository(connection)
        self._audio_fetch_fn = audio_fetch_fn
        self._audio_thread: VoicemailAudioWorker | None = None
        self._new_voicemail_count = 0
        # Player-Quelle (QByteArray/QBuffer) als Instanzattribute halten, damit sie
        # waehrend der Wiedergabe nicht vom GC eingesammelt werden (QMediaPlayer
        # haelt selbst keine Python-Referenz auf sourceDevice()).
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
        install_tristate_sorting(self._table, self._proxy)
        install_voicemail_context_menu(
            self._table,
            self._proxy,
            self._model.message_at,
            self.call_requested.emit,
            self.play_message,
            self._hide_message,
        )

        self._now_playing_label = QLabel()
        self._play_pause_button = QPushButton("▶")
        self._play_pause_button.setEnabled(False)
        self._play_pause_button.clicked.connect(self._on_play_pause_clicked)
        self._position_slider = QSlider(Qt.Orientation.Horizontal)
        self._position_slider.setEnabled(False)
        self._position_slider.sliderMoved.connect(self._player.setPosition)
        self._position_label = QLabel("0:00 / 0:00")

        transport_row = QHBoxLayout()
        transport_row.addWidget(self._play_pause_button)
        transport_row.addWidget(self._position_slider)
        transport_row.addWidget(self._position_label)

        layout = QVBoxLayout(self)
        layout.addWidget(self._now_playing_label)
        layout.addLayout(transport_row)
        layout.addWidget(self._table)

        self.reload()

    @property
    def audio_thread(self) -> VoicemailAudioWorker | None:
        return self._audio_thread

    @property
    def new_voicemail_count(self) -> int:
        return self._new_voicemail_count

    def reload(self) -> None:
        """Laedt die Nachrichtenliste neu (z.B. nach einem Sync)."""
        messages = self._voicemail_repo.list_visible()
        self._model.set_messages(messages)
        self._new_voicemail_count = sum(1 for m in messages if m.is_new)
        self.new_voicemail_count_changed.emit(self._new_voicemail_count)

    def _on_row_double_clicked(self, index) -> None:
        source_row = self._proxy.mapToSource(index).row()
        self.play_message(self._model.message_at(source_row))

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

    def _hide_message(self, message: VoicemailMessageRecord) -> None:
        self._voicemail_repo.set_hidden(message.id, True)
        self.reload()
