"""Responsive layout and native note-link tests."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QBoxLayout, QLabel, QSizePolicy

from klaus.ui.chat_widget import ChatWidget, MessageCard
from klaus.ui.file_links import reveal_file_in_browser
from klaus.ui.image_viewer import ClickableImageLabel
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


def test_voice_dock_hides_optional_text_when_narrow(qt_app) -> None:
    dock = StatusWidget()
    dock.resize(500, dock.height())
    dock.show()
    qt_app.processEvents()

    assert dock._detail_label.isHidden()
    assert dock._stats_label.isHidden()
    assert dock._mode_btn.isHidden() is False


def test_voice_dock_collapses_controls_to_stop_while_busy(qt_app) -> None:
    dock = StatusWidget(toggle_key="Shift+§")
    dock.set_state("thinking")
    dock.set_exchange_count(18)
    dock.resize(900, dock.height())
    dock.show()
    qt_app.processEvents()

    assert dock._stop_btn.isHidden() is False
    assert dock._mode_btn.isHidden()
    assert dock._stats_label.isHidden()
    assert dock._capsule.property("dockState") == "hot"

    dock.set_state("idle")
    qt_app.processEvents()
    assert dock._stop_btn.isHidden()
    assert dock._mode_btn.isHidden() is False
    assert dock._mode_btn.text() == "Shift+§  ·  Switch to hands-free"
    assert dock._capsule.property("dockState") == "calm"

    dock.close()


def test_empty_state_stacks_prompts_when_narrow(qt_app) -> None:
    chat = ChatWidget()
    chat.resize(440, 500)
    chat.show()
    qt_app.processEvents()

    assert chat._prompts.direction() == QBoxLayout.Direction.TopToBottom


def test_chat_rows_do_not_expand_into_blank_vertical_space(qt_app) -> None:
    chat = ChatWidget()
    chat.resize(900, 700)
    chat.add_message("user", "What am I looking at?")
    chat.add_status_message("Answer interrupted.")
    chat.show()
    qt_app.processEvents()

    assert all(
        row.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
        for row in chat._message_widgets
    )


def test_chat_scroll_range_ends_after_last_message(qt_app) -> None:
    chat = ChatWidget()
    chat.resize(1200, 800)
    for index in range(18):
        chat.add_message(
            "user",
            f"Question {index}: Can you tell me what I am looking at?",
        )
        chat.add_message(
            "assistant",
            "A concise answer that occupies one or two lines of text.",
        )
    chat.add_status_message("Answer interrupted.")
    chat.show()
    for _ in range(4):
        qt_app.processEvents()

    scrollbar = chat._scroll.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    qt_app.processEvents()
    last_row = chat._message_widgets[-1]
    bottom_gap = chat._container.height() - (
        last_row.y() + last_row.height()
    )

    assert bottom_gap <= chat._layout.contentsMargins().bottom() + 1


def test_streamed_answer_grows_instead_of_clipping_last_lines(qt_app) -> None:
    chat = ChatWidget()
    chat.resize(1024, 525)
    chat.show()
    for fragment in (
        "You are looking at a developer's task summary detailing fixes for a "
        "software issue called 'active window voice stop'.",
        "It reports specific updates to synthetic voice testing, interruption "
        "latency, and echo prevention, confirming all tests passed.",
        "This view appears to be within a project management or git "
        "collaboration tool.",
    ):
        chat.append_assistant_stream(fragment)
        qt_app.processEvents()
    for _ in range(3):
        qt_app.processEvents()

    card = chat._streaming_card
    row = chat._message_widgets[-1]

    assert card is not None
    assert row.height() >= row.sizeHint().height()
    assert card.height() >= card.sizeHint().height()
    assert card._body.height() >= card._body.sizeHint().height()


def test_new_screenshot_card_keeps_full_thumbnail_in_long_chat(qt_app) -> None:
    thumbnail = BytesIO()
    Image.new("RGB", (1200, 800), color=(25, 50, 75)).save(
        thumbnail, format="JPEG"
    )
    chat = ChatWidget()
    chat.resize(1024, 525)
    chat.show()
    for _ in range(8):
        chat.add_message(
            "assistant",
            "A previous response that occupies several wrapped lines. " * 6,
        )
        qt_app.processEvents()

    chat.add_message(
        "user",
        "What am I looking at?",
        thumbnail_bytes=thumbnail.getvalue(),
    )
    for _ in range(3):
        qt_app.processEvents()

    row = chat._message_widgets[-1]
    card = chat._last_card
    thumbnail_label = next(
        label
        for label in card.findChildren(QLabel)
        if label.objectName() == "card-thumbnail"
    )

    assert row.height() >= row.sizeHint().height()
    assert thumbnail_label.height() == thumbnail_label.pixmap().height()


def test_chat_screenshot_opens_full_size_image(qt_app) -> None:
    thumbnail = BytesIO()
    Image.new("RGB", (1200, 800), color=(25, 50, 75)).save(
        thumbnail, format="JPEG"
    )
    card = MessageCard(
        "user",
        "What am I looking at?",
        thumbnail_bytes=thumbnail.getvalue(),
    )
    card.show()
    qt_app.processEvents()
    thumbnail_label = card.findChild(ClickableImageLabel, "card-thumbnail")

    with patch("klaus.ui.chat_widget.show_image_viewer") as show_viewer:
        QTest.mouseClick(thumbnail_label, Qt.MouseButton.LeftButton)

    shown_pixmap = show_viewer.call_args.args[0]
    assert shown_pixmap.width() == 1200
    assert shown_pixmap.height() == 800
    assert show_viewer.call_args.kwargs["parent"] is card


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
