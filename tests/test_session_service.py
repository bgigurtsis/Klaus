"""Tests for the session service: CRUD, activation, and notes binding."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from klaus.services.session_service import SessionService, SessionView


def _session(session_id: str, title: str, updated_at: float = 1.0) -> SimpleNamespace:
    return SimpleNamespace(id=session_id, title=title, updated_at=updated_at)


def _view() -> SessionView:
    return SessionView(
        set_sessions=MagicMock(),
        set_current_title=MagicMock(),
        clear_chat=MagicMock(),
        add_chat_message=MagicMock(),
        scroll_chat_to_bottom=MagicMock(),
        emit_exchange_count=MagicMock(),
    )


def _service(memory, notes=None, view=None):
    return SessionService(
        memory,
        notes or MagicMock(),
        view or _view(),
        reset_guard_stats=MagicMock(),
        clear_brain_history=MagicMock(),
    )


def test_load_initial_creates_first_session_when_none_exist():
    memory = MagicMock()
    memory.list_sessions.return_value = []
    memory.create_session.return_value = _session("s1", "Untitled Session")
    memory.get_exchanges.return_value = []
    memory.count_exchanges.return_value = 0
    view = _view()

    service = _service(memory, view=view)
    service.load_initial()

    memory.create_session.assert_called_once_with("Untitled Session")
    assert service.current_session_id == "s1"
    view.set_sessions.assert_called_once()
    view.emit_exchange_count.assert_called_once_with(0)


def test_load_history_restores_user_thumbnail():
    memory = MagicMock()
    memory.get_exchanges.return_value = [
        SimpleNamespace(
            id="exchange-1",
            user_text="What am I looking at?",
            assistant_text="A chart.",
            created_at=123.0,
            thumbnail_bytes=b"jpeg-thumbnail",
            note_file_path=None,
        )
    ]
    view = _view()

    _service(memory, view=view).load_history("session-1")

    user_call = view.add_chat_message.call_args_list[0]
    assert user_call.kwargs["role"] == "user"
    assert user_call.kwargs["thumbnail_bytes"] == b"jpeg-thumbnail"


def test_activate_rebinds_notes_and_sets_title():
    memory = MagicMock()
    memory.list_sessions.return_value = [_session("s2", "Second")]
    memory.get_exchanges.return_value = []
    memory.count_exchanges.return_value = 3
    memory.get_session_notes_file.return_value = "Notes.md"
    memory.get_session_notes_capture_mode.return_value = "questions"
    memory.get_session_notes_capture_screenshots.return_value = True
    notes = MagicMock()
    view = _view()

    service = _service(memory, notes=notes, view=view)
    service.activate("s2")

    assert service.current_session_id == "s2"
    assert notes.current_file == "Notes.md"
    assert notes.capture_mode == "questions"
    assert notes.capture_screenshots is True
    view.set_current_title.assert_called_once_with("Second")
    view.emit_exchange_count.assert_called_once_with(3)


def test_rename_updates_title_only_for_current_session():
    memory = MagicMock()
    memory.list_sessions.return_value = [_session("s1", "Renamed")]
    memory.count_exchanges.return_value = 0
    view = _view()

    service = _service(memory, view=view)
    service.rename("s1", "Renamed")

    memory.update_session_title.assert_called_once_with("s1", "Renamed")
    view.set_current_title.assert_not_called()


def test_delete_last_session_recreates_untitled_and_activates_it():
    memory = MagicMock()
    memory.list_sessions.return_value = []
    memory.create_session.return_value = _session("fresh", "Untitled Session")
    memory.get_exchanges.return_value = []
    memory.count_exchanges.return_value = 0
    view = _view()

    service = _service(memory, view=view)
    service.delete("old")

    memory.delete_session.assert_called_once_with("old")
    memory.create_session.assert_called_once_with("Untitled Session")
    assert service.current_session_id == "fresh"
    view.set_current_title.assert_called_once_with("Untitled Session")


def test_create_resets_notes_bindings():
    memory = MagicMock()
    memory.create_session.return_value = _session("new", "Fresh")
    memory.list_sessions.return_value = [_session("new", "Fresh")]
    memory.count_exchanges.return_value = 0
    notes = MagicMock()
    view = _view()

    service = _service(memory, notes=notes, view=view)
    service.create("Fresh")

    assert notes.current_file is None
    assert notes.capture_mode == "off"
    assert notes.capture_screenshots is False
    view.clear_chat.assert_called_once()
    view.set_current_title.assert_called_once_with("Fresh")


def test_set_notes_manager_rebinds_current_session():
    memory = MagicMock()
    memory.list_sessions.return_value = [_session("s1", "One")]
    memory.get_exchanges.return_value = []
    memory.count_exchanges.return_value = 0
    memory.get_session_notes_file.return_value = "One.md"

    service = _service(memory)
    service.load_initial()
    replacement = MagicMock()
    service.set_notes_manager(replacement)

    assert replacement.current_file == "One.md"
