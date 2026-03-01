from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from klaus.config import DATA_DIR, DB_PATH

logger = logging.getLogger(__name__)


@dataclass
class Session:
    id: str
    title: str
    created_at: float
    updated_at: float
    notes_file: str | None = None


@dataclass
class ExchangeRecord:
    id: str
    session_id: str
    user_text: str
    assistant_text: str
    image_hash: str | None
    searches_json: str
    created_at: float


class Memory:
    """Persistent storage for sessions, exchanges, and knowledge profile."""

    def __init__(self, db_path: Path = DB_PATH):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Opening database at %s", db_path)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exchanges (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_text TEXT NOT NULL,
                assistant_text TEXT NOT NULL,
                image_hash TEXT,
                searches_json TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS knowledge_profile (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                summary TEXT NOT NULL,
                comfort_level TEXT NOT NULL DEFAULT 'beginner',
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_exchanges_session
                ON exchanges(session_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_knowledge_topic
                ON knowledge_profile(topic);
        """)
        self._migrate_sessions_notes_file()
        self._conn.commit()

    def _migrate_sessions_notes_file(self) -> None:
        """Add notes_file column to sessions if it doesn't exist yet."""
        cols = [
            r["name"]
            for r in self._conn.execute("PRAGMA table_info(sessions)").fetchall()
        ]
        if "notes_file" not in cols:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN notes_file TEXT")
            logger.info("Migrated sessions table: added notes_file column")

    # -- Sessions --

    def create_session(self, title: str) -> Session:
        now = time.time()
        session = Session(
            id=str(uuid.uuid4()),
            title=title,
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session.id, session.title, session.created_at, session.updated_at),
        )
        self._conn.commit()
        logger.info("Created session '%s' (%s)", title, session.id[:8])
        return session

    def list_sessions(self) -> list[Session]:
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [
            Session(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                notes_file=r["notes_file"],
            )
            for r in rows
        ]

    def update_session_title(self, session_id: str, title: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), session_id),
        )
        self._conn.commit()

    def delete_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM exchanges WHERE session_id = ?", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()

    def get_session_notes_file(self, session_id: str) -> str | None:
        """Return the notes file path for a session, or None if not set."""
        row = self._conn.execute(
            "SELECT notes_file FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row["notes_file"] if row else None

    def set_session_notes_file(self, session_id: str, notes_file: str | None) -> None:
        """Persist the notes file path for a session."""
        self._conn.execute(
            "UPDATE sessions SET notes_file = ?, updated_at = ? WHERE id = ?",
            (notes_file, time.time(), session_id),
        )
        self._conn.commit()
        logger.info(
            "Set notes_file for session %s: %s",
            session_id[:8], notes_file,
        )

    # -- Exchanges --

    def save_exchange(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        image_base64: str | None = None,
        searches: list[dict] | None = None,
    ) -> ExchangeRecord:
        now = time.time()
        image_hash = None
        if image_base64:
            image_hash = hashlib.sha256(image_base64.encode()).hexdigest()[:16]

        record = ExchangeRecord(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_text=user_text,
            assistant_text=assistant_text,
            image_hash=image_hash,
            searches_json=json.dumps(searches or []),
            created_at=now,
        )
        self._conn.execute(
            """INSERT INTO exchanges
               (id, session_id, user_text, assistant_text, image_hash, searches_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.session_id,
                record.user_text,
                record.assistant_text,
                record.image_hash,
                record.searches_json,
                record.created_at,
            ),
        )
        self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        self._conn.commit()
        logger.info("Saved exchange %s to session %s", record.id[:8], session_id[:8])
        return record

    def get_exchanges(self, session_id: str) -> list[ExchangeRecord]:
        rows = self._conn.execute(
            "SELECT * FROM exchanges WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [
            ExchangeRecord(
                id=r["id"],
                session_id=r["session_id"],
                user_text=r["user_text"],
                assistant_text=r["assistant_text"],
                image_hash=r["image_hash"],
                searches_json=r["searches_json"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def count_exchanges(self, session_id: str | None = None) -> int:
        if session_id:
            row = self._conn.execute(
                "SELECT COUNT(*) as c FROM exchanges WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) as c FROM exchanges").fetchone()
        return row["c"]

    # -- Knowledge Profile --

    def update_knowledge(self, topic: str, summary: str, comfort_level: str = "learning") -> None:
        now = time.time()
        existing = self._conn.execute(
            "SELECT id FROM knowledge_profile WHERE topic = ?", (topic,)
        ).fetchone()
        if existing:
            self._conn.execute(
                """UPDATE knowledge_profile
                   SET summary = ?, comfort_level = ?, last_seen = ?
                   WHERE id = ?""",
                (summary, comfort_level, now, existing["id"]),
            )
        else:
            self._conn.execute(
                """INSERT INTO knowledge_profile
                   (id, topic, summary, comfort_level, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), topic, summary, comfort_level, now, now),
            )
        self._conn.commit()

    def get_knowledge_summary(self, limit: int = 20) -> str:
        """Return a text summary of the user's knowledge profile for inclusion in prompts."""
        rows = self._conn.execute(
            "SELECT topic, summary, comfort_level FROM knowledge_profile ORDER BY last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return ""
        lines = []
        for r in rows:
            lines.append(f"- {r['topic']} ({r['comfort_level']}): {r['summary']}")
        return "User's knowledge profile:\n" + "\n".join(lines)

    def get_recent_exchanges_summary(self, session_id: str, limit: int = 5) -> str:
        """Return a brief summary of recent exchanges for context."""
        rows = self._conn.execute(
            """SELECT user_text, assistant_text FROM exchanges
               WHERE session_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (session_id, limit),
        ).fetchall()
        if not rows:
            return ""
        lines = []
        for r in reversed(rows):
            q = r["user_text"][:100]
            a = r["assistant_text"][:150]
            lines.append(f"Q: {q}\nA: {a}")
        return "Recent exchanges in this session:\n" + "\n".join(lines)

    def close(self) -> None:
        self._conn.close()
