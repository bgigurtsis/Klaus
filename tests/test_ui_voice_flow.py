"""Focused UI tests for Klaus's voice and interruption states."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from klaus.ui.chat_widget import ChatWidget
from klaus.ui.status_widget import StatusWidget


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_voice_dock_makes_interruption_primary(qt_app) -> None:
    dock = StatusWidget(mode="voice_activation")

    dock.set_state("speaking")

    assert dock._state_label.text() == "Answering"
    assert "Speak to interrupt" in dock._detail_label.text()
    assert dock._stop_btn.text() == "Interrupt"
    assert dock._stop_btn.isHidden() is False


def test_voice_dock_explains_each_input_mode(qt_app) -> None:
    dock = StatusWidget(hotkey="F2", toggle_key="F3")

    dock.set_mode("push_to_talk")
    dock.set_state("idle")

    assert dock._mode_btn.text() == "Push to talk"
    assert dock._detail_label.text() == "Hold F2 to ask a question"
    assert "hands-free" in dock._hotkey_label.text()


def test_interrupted_stream_stays_visible_and_marked(qt_app) -> None:
    chat = ChatWidget()
    chat.append_assistant_stream("The answer")
    chat.append_assistant_stream(" starts here.")
    card = chat._streaming_card

    chat.abort_assistant_stream()

    assert card is not None
    assert card._body.text() == "The answer starts here."
    assert card._status_label.text() == "Interrupted"
    assert card._status_label.isHidden() is False


def test_streamed_text_preserves_provider_fragment_boundaries(qt_app) -> None:
    chat = ChatWidget()

    chat.append_assistant_stream("Stream")
    chat.append_assistant_stream("ing text")
    chat.append_assistant_stream(" as it arrives.")

    assert chat._streaming_card is not None
    assert chat._streaming_card._body.text() == "Streaming text as it arrives."
