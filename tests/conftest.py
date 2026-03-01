import os
import tempfile
from pathlib import Path

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
