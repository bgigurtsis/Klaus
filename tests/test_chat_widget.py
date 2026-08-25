"""Tests for the chat feed: streaming, thinking placeholder, teardown."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from klaus.ui.chat_widget import _THINKING_FRAMES, ChatWidget


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def chat(qt_app):
    widget = ChatWidget()
    yield widget
    widget.deleteLater()


def _card_count(chat: ChatWidget) -> int:
    return len(chat._message_widgets)


def test_show_thinking_creates_pending_assistant_card(chat):
    chat.show_thinking()

    assert _card_count(chat) == 1
    assert chat._streaming_card is not None
    assert chat._streaming_card._text in _THINKING_FRAMES
    assert chat._thinking_timer.isActive()


def test_first_fragment_replaces_thinking_placeholder(chat):
    chat.show_thinking()
    chat.append_assistant_stream("The answer starts")

    assert chat._streaming_card._text == "The answer starts"
    assert not chat._thinking_timer.isActive()
    assert _card_count(chat) == 1

    chat.append_assistant_stream(" and continues.")
    assert chat._streaming_card._text == "The answer starts and continues."


def test_finalize_replaces_placeholder_text(chat):
    chat.show_thinking()

    assert chat.finalize_assistant_stream("Full answer.", "exchange-1") is True
    assert chat._streaming_card is None
    assert not chat._thinking_timer.isActive()
    assert _card_count(chat) == 1


def test_abort_removes_placeholder_without_interrupted_mark(chat):
    chat.show_thinking()
    chat.abort_assistant_stream()

    assert _card_count(chat) == 0
    assert chat._streaming_card is None
    assert not chat._thinking_timer.isActive()
    assert not chat._empty_state.isHidden()


def test_abort_after_text_marks_interrupted_and_keeps_card(chat):
    chat.show_thinking()
    chat.append_assistant_stream("Partial answer")
    chat.abort_assistant_stream()

    assert _card_count(chat) == 1
    assert chat._streaming_card is None


def test_dismiss_thinking_is_noop_after_text_arrived(chat):
    chat.show_thinking()
    chat.append_assistant_stream("Answer text")
    chat.dismiss_thinking()

    assert _card_count(chat) == 1
    assert chat._streaming_card is not None


def test_show_thinking_is_noop_while_streaming(chat):
    chat.append_assistant_stream("Already streaming")
    chat.show_thinking()

    assert _card_count(chat) == 1
    assert not chat._thinking_timer.isActive()


def test_streaming_without_placeholder_still_works(chat):
    chat.append_assistant_stream("Hello")
    chat.append_assistant_stream(" world")

    assert chat.finalize_assistant_stream("Hello world", "exchange-2") is True
    assert _card_count(chat) == 1


def test_clear_stops_thinking_timer(chat):
    chat.show_thinking()
    chat.clear()

    assert _card_count(chat) == 0
    assert not chat._thinking_timer.isActive()
