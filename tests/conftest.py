import pytest


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch):
    """Ensure tests never use real API keys."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")


@pytest.fixture
def tmp_db(tmp_path):
    """Return a path to a temporary SQLite database file."""
    return tmp_path / "test_klaus.db"
