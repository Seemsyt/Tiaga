from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from tiaga.client.response import TokenUsage
from tiaga.config.loader import get_data_dir


@dataclass
class SessionSnapshot:
    session_id: str
    created_at: datetime
    updated_at: datetime
    turn_count: int
    messages: list[dict[str, Any]]
    total_usage: TokenUsage
    title: str = ""                          # ← new: human-readable label

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "turn_count": self.turn_count,
            "messages": self.messages,
            "total_usage": self.total_usage.__dict__,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionSnapshot:
        return cls(
            session_id=data["session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            turn_count=data["turn_count"],
            messages=data["messages"],
            total_usage=TokenUsage(**data["total_usage"]),
            title=data.get("title", ""),
        )


class PersistenceManager:
    DB_NAME = "sessions.db"
    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            title       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            turn_count  INTEGER NOT NULL DEFAULT 0,
            messages    TEXT NOT NULL DEFAULT '[]',
            total_usage TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS checkpoints (
            checkpoint_id TEXT PRIMARY KEY,
            session_id    TEXT NOT NULL,
            title         TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            turn_count    INTEGER NOT NULL DEFAULT 0,
            messages      TEXT NOT NULL DEFAULT '[]',
            total_usage   TEXT NOT NULL DEFAULT '{}'
        );
    """

    # Migration: add title column to existing databases that pre-date this field
    _MIGRATIONS = [
        "ALTER TABLE sessions    ADD COLUMN title TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE checkpoints ADD COLUMN title TEXT NOT NULL DEFAULT ''",
    ]

    def __init__(self) -> None:
        self.data_dir: Path = get_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.db_path: Path = self.data_dir / self.DB_NAME
        self._init_db()
        self._migrate()

        # Restrict access to the database file
        os.chmod(self.db_path, 0o600)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(self._SCHEMA)

    def _migrate(self) -> None:
        """Apply any missing schema migrations idempotently."""
        for sql in self._MIGRATIONS:
            try:
                with self._connect() as con:
                    con.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists — safe to ignore

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=row["session_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            turn_count=row["turn_count"],
            messages=json.loads(row["messages"]),
            total_usage=TokenUsage(**json.loads(row["total_usage"])),
            title=row["title"] if "title" in row.keys() else "",
        )

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def save_session(self, snapshot: SessionSnapshot) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO sessions (session_id, title, created_at, updated_at, turn_count, messages, total_usage)
                VALUES (:session_id, :title, :created_at, :updated_at, :turn_count, :messages, :total_usage)
                ON CONFLICT(session_id) DO UPDATE SET
                    title       = excluded.title,
                    updated_at  = excluded.updated_at,
                    turn_count  = excluded.turn_count,
                    messages    = excluded.messages,
                    total_usage = excluded.total_usage
                """,
                {
                    "session_id": snapshot.session_id,
                    "title": snapshot.title,
                    "created_at": snapshot.created_at.isoformat(),
                    "updated_at": snapshot.updated_at.isoformat(),
                    "turn_count": snapshot.turn_count,
                    "messages": json.dumps(snapshot.messages),
                    "total_usage": json.dumps(snapshot.total_usage.__dict__),
                },
            )

    def load_session(self, session_id: str) -> SessionSnapshot | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return self._row_to_snapshot(row) if row else None

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT session_id, title, created_at, updated_at, turn_count
                FROM sessions
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def update_session_title(self, session_id: str, title: str) -> bool:
        """Returns True if the session was found and updated."""
        with self._connect() as con:
            cur = con.execute(
                "UPDATE sessions SET title = ? WHERE session_id = ?",
                (title, session_id),
            )
        return cur.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        """Returns True if a row was deleted."""
        with self._connect() as con:
            cur = con.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def save_checkpoint(self, snapshot: SessionSnapshot) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_id = f"{snapshot.session_id}_{timestamp}"

        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                    (checkpoint_id, session_id, title, created_at, updated_at, turn_count, messages, total_usage)
                VALUES
                    (:checkpoint_id, :session_id, :title, :created_at, :updated_at, :turn_count, :messages, :total_usage)
                """,
                {
                    "checkpoint_id": checkpoint_id,
                    "session_id": snapshot.session_id,
                    "title": snapshot.title,
                    "created_at": snapshot.created_at.isoformat(),
                    "updated_at": snapshot.updated_at.isoformat(),
                    "turn_count": snapshot.turn_count,
                    "messages": json.dumps(snapshot.messages),
                    "total_usage": json.dumps(snapshot.total_usage.__dict__),
                },
            )
        return checkpoint_id

    def load_checkpoint(self, checkpoint_id: str) -> SessionSnapshot | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
            ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def list_checkpoints(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT checkpoint_id, session_id, title, created_at, updated_at, turn_count
                FROM checkpoints
                WHERE session_id = ?
                ORDER BY created_at DESC
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        with self._connect() as con:
            cur = con.execute(
                "DELETE FROM checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
            )
        return cur.rowcount > 0