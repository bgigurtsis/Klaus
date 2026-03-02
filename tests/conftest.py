import os
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch):
    """Ensure tests never use real API keys."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")


@pytest.fixture
def tmp_db(tmp_path):
    """Return a path to a temporary SQLite database file."""
    return tmp_path / "test_klaus.db"


class FakeAnthropicStream:
    def __init__(self, response, events=None):
        self._response = response
        self._events = events or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._response


@pytest.fixture
def anthropic_stream_tools():
    def make_response(text: str, stop_reason: str = "end_turn"):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason=stop_reason,
        )

    def make_delta_event(text: str):
        return SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(text=text),
        )

    return SimpleNamespace(
        stream=FakeAnthropicStream,
        response=make_response,
        delta=make_delta_event,
    )
