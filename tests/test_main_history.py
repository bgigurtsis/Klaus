"""Tests for restoring persisted session history in the app coordinator."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from klaus.main import KlausApp


def test_load_session_history_restores_user_thumbnail() -> None:
    app = KlausApp.__new__(KlausApp)
    app._window = MagicMock()
    app._memory = MagicMock()
    app._memory.get_exchanges.return_value = [
        SimpleNamespace(
            id="exchange-1",
            user_text="What am I looking at?",
            assistant_text="A chart.",
            created_at=123.0,
            thumbnail_bytes=b"jpeg-thumbnail",
            note_file_path=None,
        )
    ]

    KlausApp._load_session_history(app, "session-1")

    user_call = app._window.chat_widget.add_message.call_args_list[0]
    assert user_call.kwargs["role"] == "user"
    assert user_call.kwargs["thumbnail_bytes"] == b"jpeg-thumbnail"
