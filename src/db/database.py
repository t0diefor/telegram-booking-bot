"""Async SQLite access layer.

Everything the bot needs to remember lives here: who the user is, what
state they're in, recent conversation turns (for LLM context), and
confirmed bookings. Nothing is kept only in memory, so a bot restart
mid-conversation does not lose the user's place (Phase 9 test case).
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

logger = logging.getLogger("bot.db")

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Session:
    user_id: int
    state: str
    context: dict[str, Any]


class Database:
    """Thin async wrapper. One instance per process, opened once at startup."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        schema = SCHEMA_PATH.read_text()
        await self._conn.executescript(schema)
        await self._conn.commit()
        logger.info("database ready at %s", self._db_path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() must be called before use")
        return self._conn

    # -- users -----------------------------------------------------------

    async def upsert_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        now = _now()
        await self.conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, created_at, last_active_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_active_at = excluded.last_active_at
            """,
            (user_id, username, first_name, now, now),
        )
        await self.conn.commit()

    # -- sessions (state machine) -----------------------------------------

    async def get_session(self, user_id: int) -> Session:
        cur = await self.conn.execute(
            "SELECT user_id, state, context_json FROM sessions WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return Session(user_id=user_id, state="idle", context={})
        return Session(user_id=user_id, state=row["state"], context=json.loads(row["context_json"]))

    async def set_session(self, user_id: int, state: str, context: dict[str, Any]) -> None:
        now = _now()
        await self.conn.execute(
            """
            INSERT INTO sessions (user_id, state, context_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                state = excluded.state,
                context_json = excluded.context_json,
                updated_at = excluded.updated_at
            """,
            (user_id, state, json.dumps(context), now),
        )
        await self.conn.commit()

    # -- conversation history ---------------------------------------------

    async def append_history(self, user_id: int, role: str, content: str) -> None:
        await self.conn.execute(
            "INSERT INTO conversation_history (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, _now()),
        )
        await self.conn.commit()

    async def get_recent_history(self, user_id: int, limit: int = 6) -> list[dict[str, str]]:
        """Last `limit` turns, oldest first, ready to feed straight into an LLM messages list."""
        cur = await self.conn.execute(
            """
            SELECT role, content FROM conversation_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = await cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def prune_old_history(self, max_age_days: int) -> int:
        """Delete conversation turns older than max_age_days. Returns rows deleted.

        Bookings are never pruned here - only chat context, which is what
        the requirements call out as needing to not grow unbounded.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        cur = await self.conn.execute(
            "DELETE FROM conversation_history WHERE created_at < ?", (cutoff,)
        )
        await self.conn.commit()
        deleted = cur.rowcount if cur.rowcount is not None else 0
        if deleted:
            logger.info("pruned %d old conversation_history rows", deleted)
        return deleted

    # -- bookings -----------------------------------------------------------

    async def create_booking(self, user_id: int, service: str, booking_date: str, booking_time: str) -> int:
        cur = await self.conn.execute(
            """
            INSERT INTO bookings (user_id, service, booking_date, booking_time, status, created_at)
            VALUES (?, ?, ?, ?, 'confirmed', ?)
            """,
            (user_id, service, booking_date, booking_time, _now()),
        )
        await self.conn.commit()
        return cur.lastrowid


@asynccontextmanager
async def open_database(db_path: Path) -> AsyncIterator[Database]:
    db = Database(db_path)
    await db.connect()
    try:
        yield db
    finally:
        await db.close()
