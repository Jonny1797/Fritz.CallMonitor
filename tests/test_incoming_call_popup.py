from PySide6.QtWidgets import QLabel, QPushButton

from fritz_callhistory.gui.incoming_call_popup import IncomingCallPopup


def _label_texts(popup: IncomingCallPopup) -> str:
    return " ".join(label.text() for label in popup.findChildren(QLabel))


def test_popup_shows_title_subtitle_and_notes(qtbot):
    popup = IncomingCallPopup(
        "0", "Max Mustermann", "+49301234567", "Ruft oft wegen der Miete an", 1
    )
    qtbot.addWidget(popup)

    text = _label_texts(popup)
    assert "Max Mustermann" in text
    assert "+49301234567" in text
    assert "Ruft oft wegen der Miete an" in text


def test_popup_without_notes_has_no_notes_label(qtbot):
    with_notes = IncomingCallPopup("0", "Max Mustermann", "+49301234567", "Notiz", 1)
    without_notes = IncomingCallPopup("1", "Max Mustermann", "+49301234567", None, 1)
    qtbot.addWidget(with_notes)
    qtbot.addWidget(without_notes)

    assert len(without_notes.findChildren(QLabel)) < len(with_notes.findChildren(QLabel))
    assert "Max Mustermann" in _label_texts(without_notes)


def test_popup_shows_open_contact_button_when_contact_id_given(qtbot):
    popup = IncomingCallPopup("0", "Max Mustermann", "+49301234567", None, 1)
    qtbot.addWidget(popup)

    button_labels = [button.text() for button in popup.findChildren(QPushButton)]
    assert "Kontakt anzeigen" in button_labels
    assert "Schließen" in button_labels


def test_popup_hides_open_contact_button_without_contact_id(qtbot):
    popup = IncomingCallPopup("0", "Unbekannt", "", None, None)
    qtbot.addWidget(popup)

    button_labels = [button.text() for button in popup.findChildren(QPushButton)]
    assert "Kontakt anzeigen" not in button_labels
    assert "Schließen" in button_labels


def test_clicking_open_contact_emits_signal_and_closes(qtbot):
    popup = IncomingCallPopup("0", "Max Mustermann", "+49301234567", None, 42)
    qtbot.addWidget(popup)

    open_contact_button = next(
        button for button in popup.findChildren(QPushButton) if button.text() == "Kontakt anzeigen"
    )
    with qtbot.waitSignal(popup.open_contact_requested, timeout=1000) as blocker:
        open_contact_button.click()

    assert blocker.args == [42]
    assert popup.isVisible() is False


def test_clicking_close_button_closes_popup_without_emitting_signal(qtbot):
    popup = IncomingCallPopup("0", "Max Mustermann", "+49301234567", None, 42)
    qtbot.addWidget(popup)
    popup.show()

    emitted = []
    popup.open_contact_requested.connect(emitted.append)
    close_button = next(
        button for button in popup.findChildren(QPushButton) if button.text() == "Schließen"
    )
    close_button.click()

    assert emitted == []
    assert popup.isVisible() is False
