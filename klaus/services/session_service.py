"""Session CRUD and the shared session-activation flow.

Owns which session is current, keeps the NotesManager bound to that
session's notes settings, and drives the session list, chat history, and
exchange count through a small view surface. KlausApp keeps thin
signal-connected slots that delegate here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionView:
    """UI operations the session flow needs, as plain callables."""

    set_sessions: Callable[[list[dict], str], None]
    set_current_title: Callable[[str], None]
    clear_chat: Callable[[], None]
    add_chat_message: Callable[..., None]
    scroll_chat_to_bottom: Callable[[], None]
    emit_exchange_count: Callable[[int], None]


class SessionService:
    def __init__(
        self,
        memory,
        notes,
        view: SessionView,
        *,
        reset_guard_stats: Callable[[], None],
        clear_brain_history: Callable[[], None],
    ) -> None:
        self._memory = memory
        self._notes = notes
        self._view = view
        self._reset_guard_stats = reset_guard_stats
        self._clear_brain_history = clear_brain_history
        self._current_session_id: str | None = None

    @property
    def current_session_id(self) -> str | None:
        return self._current_session_id

    def set_notes_manager(self, notes) -> None:
        """Swap the NotesManager (e.g. after a vault change) and re-bind it."""
        self._notes = notes
        if self._current_session_id:
            self.sync_notes_bindings(self._current_session_id)

    # -- Lifecycle --

    def load_initial(self) -> None:
        """Load sessions at startup, creating the first one if none exist."""
        sessions = self._memory.list_sessions()
        if not sessions:
            sessions = [self._memory.create_session("Untitled Session")]

        self._current_session_id = sessions[0].id
        self._reset_guard_stats()
        self._view.set_sessions(
            self._build_session_dicts(sessions), self._current_session_id
        )
        logger.info(
            "Loaded %d session(s), active: '%s'", len(sessions), sessions[0].title
        )
        self.load_history(self._current_session_id)
        self.sync_notes_bindings(self._current_session_id)
        self.update_exchange_count()

    def activate(self, session_id: str) -> None:
        """Switch to a session: rebind notes, reload history, update the UI."""
        logger.info("Switched to session %s", session_id[:8])
        self._current_session_id = session_id
        self._reset_guard_stats()
        self._clear_brain_history()
        self.sync_notes_bindings(session_id)
        self.load_history(session_id)
        self._view.scroll_chat_to_bottom()
        self.update_exchange_count()

        for session in self._memory.list_sessions():
            if session.id == session_id:
                self._view.set_current_title(session.title)
                break

    def create(self, title: str) -> None:
        session = self._memory.create_session(title)
        self._current_session_id = session.id
        self._reset_guard_stats()
        self._clear_brain_history()
        self._notes.current_file = None
        self._notes.capture_mode = "off"
        self._notes.capture_screenshots = False

        self.refresh_list()
        self._view.clear_chat()
        self._view.set_current_title(title)
        self.update_exchange_count()

    def rename(self, session_id: str, new_title: str) -> None:
        logger.info("Renaming session %s to '%s'", session_id[:8], new_title)
        self._memory.update_session_title(session_id, new_title)
        self.refresh_list()
        if session_id == self._current_session_id:
            self._view.set_current_title(new_title)

    def delete(self, session_id: str) -> None:
        logger.info("Deleting session %s", session_id[:8])
        self._memory.delete_session(session_id)

        sessions = self._memory.list_sessions()
        if not sessions:
            sessions = [self._memory.create_session("Untitled Session")]

        self._current_session_id = sessions[0].id
        self._reset_guard_stats()
        self._view.set_sessions(
            self._build_session_dicts(sessions), self._current_session_id
        )
        self._view.set_current_title(sessions[0].title)
        self._clear_brain_history()
        self.sync_notes_bindings(self._current_session_id)
        self.load_history(self._current_session_id)
        self._view.scroll_chat_to_bottom()
        self.update_exchange_count()

    # -- Shared pieces --

    def refresh_list(self) -> None:
        """Reload and repopulate the session panel."""
        sessions = self._memory.list_sessions()
        self._view.set_sessions(
            self._build_session_dicts(sessions), self._current_session_id
        )

    def update_exchange_count(self) -> None:
        """Emit the per-session exchange count."""
        if self._current_session_id:
            count = self._memory.count_exchanges(self._current_session_id)
        else:
            count = 0
        self._view.emit_exchange_count(count)

    def load_history(self, session_id: str) -> None:
        self._view.clear_chat()
        for ex in self._memory.get_exchanges(session_id):
            self._view.add_chat_message(
                role="user",
                text=ex.user_text,
                timestamp=ex.created_at,
                thumbnail_bytes=ex.thumbnail_bytes,
                exchange_id=ex.id,
            )
            self._view.add_chat_message(
                role="assistant",
                text=ex.assistant_text,
                timestamp=ex.created_at,
                exchange_id=ex.id,
                note_file_path=ex.note_file_path,
            )

    def sync_notes_bindings(self, session_id: str) -> None:
        """Point the NotesManager at the session's stored notes settings."""
        self._notes.current_file = self._memory.get_session_notes_file(session_id)
        self._notes.capture_mode = self._memory.get_session_notes_capture_mode(
            session_id
        )
        self._notes.capture_screenshots = (
            self._memory.get_session_notes_capture_screenshots(session_id)
        )

    def _build_session_dicts(self, sessions) -> list[dict]:
        """Build enriched session dicts with exchange counts for the UI."""
        return [
            {
                "id": s.id,
                "title": s.title,
                "updated_at": s.updated_at,
                "exchange_count": self._memory.count_exchanges(s.id),
            }
            for s in sessions
        ]
