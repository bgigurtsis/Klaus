"""Responsive layout and native note-link tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication, QBoxLayout

from klaus.ui.chat_widget import ChatWidget, MessageCard
from klaus.ui.file_links import reveal_file_in_browser
from klaus.ui.main_window import MainWindow
from klaus.ui.status_widget import StatusWidget


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_collapses_sidebar_at_compact_width(qt_app) -> None:
    window = MainWindow()
    window.resize(700, 560)
    window.show()
    qt_app.processEvents()

    assert window.minimumWidth() == 680
    assert window.centralWidget().layout().indexOf(window._splitter) == 0
    assert window._splitter.width() == window.centralWidget().width()
    assert window._left_panel.isHidden()
    assert window._sidebar_btn.accessibleName() == "Show library sidebar"

    window.close()


def test_voice_dock_reflows_and_hides_optional_text(qt_app) -> None:
    dock = StatusWidget()
    dock.resize(500, dock.height())
    dock.show()
    qt_app.processEvents()

    assert dock._compact_layout is True
    assert dock.height() == 138
    assert dock._hotkey_label.isHidden()
    assert dock._stats_label.isHidden()


def test_empty_state_stacks_prompts_when_narrow(qt_app) -> None:
    chat = ChatWidget()
    chat.resize(440, 500)
    chat.show()
    qt_app.processEvents()

    assert chat._prompts.direction() == QBoxLayout.Direction.TopToBottom


def test_note_card_exposes_a_finder_link(qt_app, tmp_path) -> None:
    note = tmp_path / "Research Notes.md"
    note.write_text("# Notes\n", encoding="utf-8")
    card = MessageCard("assistant", "Saved.", note_file_path=str(note))

    assert not card._note_link.isHidden()
    assert "Research Notes.md" in card._note_link.text()
    assert "Finder" in card._note_link.text()

    with patch("klaus.ui.chat_widget.reveal_file_in_browser") as reveal:
        card._note_link.linkActivated.emit(QUrl.fromLocalFile(str(note)).toString())

    reveal.assert_called_once_with(str(note))


def test_macos_note_link_reveals_file_in_finder(tmp_path) -> None:
    note = tmp_path / "Research Notes.md"
    note.write_text("# Notes\n", encoding="utf-8")

    with patch(
        "klaus.ui.file_links.QProcess.startDetached", return_value=True,
    ) as start_detached:
        assert reveal_file_in_browser(str(note))

    start_detached.assert_called_once_with("open", ["-R", str(note.resolve())])
