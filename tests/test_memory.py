"""Tests for klaus.memory -- SQLite persistent storage.

These tests use a real SQLite database in a temp directory, no mocks needed.
"""

import json
import time

import pytest

from klaus.memory import Memory, Session, ExchangeRecord


@pytest.fixture
def mem(tmp_db):
    m = Memory(db_path=tmp_db)
    yield m
    m.close()


class TestSessions:
    def test_create_session(self, mem):
        session = mem.create_session("Test Paper")
        assert session.title == "Test Paper"
        assert session.id
        assert session.created_at > 0
        assert session.created_at == session.updated_at

    def test_list_sessions_empty(self, mem):
        assert mem.list_sessions() == []

    def test_list_sessions_ordering(self, mem):
        s1 = mem.create_session("First")
        time.sleep(0.01)
        s2 = mem.create_session("Second")

        sessions = mem.list_sessions()
        assert len(sessions) == 2
        assert sessions[0].title == "Second"
        assert sessions[1].title == "First"

    def test_update_session_title(self, mem):
        session = mem.create_session("Old Title")
        mem.update_session_title(session.id, "New Title")

        sessions = mem.list_sessions()
        assert sessions[0].title == "New Title"

    def test_delete_session(self, mem):
        session = mem.create_session("To Delete")
        mem.save_exchange(session.id, "Q?", "A.")
        assert mem.count_exchanges(session.id) == 1

        mem.delete_session(session.id)
        assert mem.list_sessions() == []
        assert mem.count_exchanges(session.id) == 0

    def test_delete_session_cascades_exchanges(self, mem):
        s = mem.create_session("Paper")
        mem.save_exchange(s.id, "Q1", "A1")
        mem.save_exchange(s.id, "Q2", "A2")
        assert mem.count_exchanges() == 2

        mem.delete_session(s.id)
        assert mem.count_exchanges() == 0


class TestExchanges:
    def test_save_and_get_exchanges(self, mem):
        s = mem.create_session("Paper")
        mem.save_exchange(s.id, "What is entropy?", "Entropy measures disorder.")
        mem.save_exchange(s.id, "And information?", "Information is negative entropy.")

        exchanges = mem.get_exchanges(s.id)
        assert len(exchanges) == 2
        assert exchanges[0].user_text == "What is entropy?"
        assert exchanges[1].assistant_text == "Information is negative entropy."

    def test_exchange_ordering_is_chronological(self, mem):
        s = mem.create_session("Paper")
        mem.save_exchange(s.id, "First", "A1")
        time.sleep(0.01)
        mem.save_exchange(s.id, "Second", "A2")

        exchanges = mem.get_exchanges(s.id)
        assert exchanges[0].user_text == "First"
        assert exchanges[1].user_text == "Second"
        assert exchanges[0].created_at < exchanges[1].created_at

    def test_exchange_with_image_hash(self, mem):
        s = mem.create_session("Paper")
        record = mem.save_exchange(
            s.id, "Q?", "A.", image_base64="base64imagedata"
        )
        assert record.image_hash is not None
        assert len(record.image_hash) == 16

    def test_exchange_without_image(self, mem):
        s = mem.create_session("Paper")
        record = mem.save_exchange(s.id, "Q?", "A.")
        assert record.image_hash is None

    def test_exchange_with_searches(self, mem):
        s = mem.create_session("Paper")
        searches = [{"query": "p-value meaning", "result": "A p-value is..."}]
        record = mem.save_exchange(s.id, "Q?", "A.", searches=searches)

        exchanges = mem.get_exchanges(s.id)
        stored = json.loads(exchanges[0].searches_json)
        assert len(stored) == 1
        assert stored[0]["query"] == "p-value meaning"

    def test_count_exchanges_total(self, mem):
        s1 = mem.create_session("Paper 1")
        s2 = mem.create_session("Paper 2")
        mem.save_exchange(s1.id, "Q1", "A1")
        mem.save_exchange(s2.id, "Q2", "A2")
        mem.save_exchange(s2.id, "Q3", "A3")

        assert mem.count_exchanges() == 3
        assert mem.count_exchanges(s1.id) == 1
        assert mem.count_exchanges(s2.id) == 2

    def test_save_exchange_updates_session_timestamp(self, mem):
        s = mem.create_session("Paper")
        original_updated = mem.list_sessions()[0].updated_at
        time.sleep(0.01)
        mem.save_exchange(s.id, "Q?", "A.")
        new_updated = mem.list_sessions()[0].updated_at
        assert new_updated > original_updated

    def test_get_exchanges_empty_session(self, mem):
        s = mem.create_session("Empty")
        assert mem.get_exchanges(s.id) == []

    def test_get_exchanges_wrong_session_id(self, mem):
        assert mem.get_exchanges("nonexistent-id") == []


class TestKnowledgeProfile:
    def test_insert_knowledge(self, mem):
        mem.update_knowledge("entropy", "Measures disorder in a system")
        summary = mem.get_knowledge_summary()
        assert "entropy" in summary
        assert "Measures disorder" in summary

    def test_update_existing_knowledge(self, mem):
        mem.update_knowledge("entropy", "Basic concept")
        mem.update_knowledge("entropy", "Advanced understanding", "comfortable")
        summary = mem.get_knowledge_summary()
        assert "Advanced understanding" in summary
        assert "comfortable" in summary
        assert summary.count("entropy") == 1

    def test_multiple_topics(self, mem):
        mem.update_knowledge("entropy", "Disorder measure")
        mem.update_knowledge("p-value", "Statistical significance")
        mem.update_knowledge("bayesian", "Prior probability")
        summary = mem.get_knowledge_summary()
        assert "entropy" in summary
        assert "p-value" in summary
        assert "bayesian" in summary

    def test_knowledge_summary_empty(self, mem):
        assert mem.get_knowledge_summary() == ""

    def test_knowledge_summary_limit(self, mem):
        for i in range(10):
            mem.update_knowledge(f"topic_{i}", f"Summary {i}")
        summary = mem.get_knowledge_summary(limit=3)
        assert summary.count("- ") == 3


class TestRecentExchangesSummary:
    def test_recent_summary(self, mem):
        s = mem.create_session("Paper")
        mem.save_exchange(s.id, "What is X?", "X is a variable.")
        mem.save_exchange(s.id, "And Y?", "Y is another variable.")

        summary = mem.get_recent_exchanges_summary(s.id)
        assert "What is X?" in summary
        assert "And Y?" in summary

    def test_recent_summary_empty(self, mem):
        s = mem.create_session("Paper")
        assert mem.get_recent_exchanges_summary(s.id) == ""

    def test_recent_summary_respects_limit(self, mem):
        s = mem.create_session("Paper")
        for i in range(10):
            mem.save_exchange(s.id, f"Q{i}", f"A{i}")

        summary = mem.get_recent_exchanges_summary(s.id, limit=2)
        assert "Q8" in summary or "Q9" in summary
        assert "Q0" not in summary
