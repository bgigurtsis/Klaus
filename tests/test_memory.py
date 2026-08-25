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

    def test_note_capture_mode_persists_per_session(self, mem):
        session = mem.create_session("Paper")

        mem.set_session_notes_capture_mode(session.id, "conversation")

        assert mem.get_session_notes_capture_mode(session.id) == "conversation"
        assert mem.list_sessions()[0].notes_capture_mode == "conversation"

        mem.set_session_notes_capture_screenshots(session.id, True)

        assert mem.get_session_notes_capture_screenshots(session.id) is True
        assert mem.list_sessions()[0].notes_capture_screenshots is True

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

    def test_exchange_with_thumbnail(self, mem):
        s = mem.create_session("Paper")
        record = mem.save_exchange(
            s.id,
            "Q?",
            "A.",
            thumbnail_bytes=b"jpeg-thumbnail",
        )

        assert record.thumbnail_bytes == b"jpeg-thumbnail"
        assert mem.get_exchange(record.id).thumbnail_bytes == b"jpeg-thumbnail"
        assert mem.get_exchanges(s.id)[0].thumbnail_bytes == b"jpeg-thumbnail"

    def test_thumbnail_survives_database_reopen(self, tmp_db):
        first = Memory(db_path=tmp_db)
        session = first.create_session("Paper")
        first.save_exchange(
            session.id,
            "Q?",
            "A.",
            thumbnail_bytes=b"jpeg-thumbnail",
        )
        first.close()

        reopened = Memory(db_path=tmp_db)
        try:
            assert reopened.get_exchanges(session.id)[0].thumbnail_bytes == b"jpeg-thumbnail"
        finally:
            reopened.close()

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

    def test_exchange_persists_note_file_link(self, mem, tmp_path):
        session = mem.create_session("Paper")
        note_path = str(tmp_path / "Research Notes.md")
        record = mem.save_exchange(
            session.id,
            "Save this",
            "Saved.",
            note_file_path=note_path,
        )

        assert record.note_file_path == note_path
        assert mem.get_exchange(record.id).note_file_path == note_path
        assert mem.get_exchanges(session.id)[0].note_file_path == note_path

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


