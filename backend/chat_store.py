"""Persistent store for chat conversation history.

Uses a separate SQLite file (``data/chats.db``) so the patient DB can stay
opened read-only and a re-ingest won't blow away conversations.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

from .config import DATA_DIR

CHATS_DB_PATH = DATA_DIR / "chats.db"

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CHATS_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id         TEXT PRIMARY KEY,
            title      TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id)
                            ON DELETE CASCADE,
            seq             INTEGER NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL DEFAULT '',
            tool_calls_json TEXT,
            tool_call_id    TEXT,
            name            TEXT,
            created_at      REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conv
            ON messages(conversation_id, seq);
        CREATE INDEX IF NOT EXISTS idx_conv_updated
            ON conversations(updated_at DESC);
        """
    )
    conn.commit()


@contextmanager
def _db():
    with _lock:
        conn = _connect()
        _init(conn)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


# --- Conversations ----------------------------------------------------------

def list_conversations() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT c.id, c.title, c.created_at, c.updated_at, "
            "       (SELECT COUNT(*) FROM messages m "
            "        WHERE m.conversation_id = c.id "
            "          AND m.role IN ('user','assistant')) AS message_count "
            "FROM conversations c ORDER BY c.updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def create_conversation(title: str = "") -> dict:
    now = time.time()
    cid = uuid.uuid4().hex[:16]
    with _db() as conn:
        conn.execute(
            "INSERT INTO conversations(id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (cid, title, now, now),
        )
    return {"id": cid, "title": title,
            "created_at": now, "updated_at": now, "message_count": 0}


def rename_conversation(cid: str, title: str) -> dict | None:
    with _db() as conn:
        cur = conn.execute(
            "UPDATE conversations SET title=?, updated_at=? WHERE id=?",
            (title, time.time(), cid),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations "
            "WHERE id=?",
            (cid,),
        ).fetchone()
        return dict(row) if row else None


def delete_conversation(cid: str) -> bool:
    with _db() as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
        return cur.rowcount > 0


def get_conversation(cid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations "
            "WHERE id=?",
            (cid,),
        ).fetchone()
        if not row:
            return None
        msgs = conn.execute(
            "SELECT role, content, tool_calls_json, tool_call_id, name, seq "
            "FROM messages WHERE conversation_id=? ORDER BY seq",
            (cid,),
        ).fetchall()
    out = dict(row)
    out["messages"] = [_row_to_message(m) for m in msgs]
    return out


def _row_to_message(row: sqlite3.Row) -> dict:
    m: dict = {"role": row["role"], "content": row["content"] or ""}
    if row["tool_calls_json"]:
        try:
            m["tool_calls"] = json.loads(row["tool_calls_json"])
        except json.JSONDecodeError:
            pass
    if row["tool_call_id"]:
        m["tool_call_id"] = row["tool_call_id"]
    if row["name"]:
        m["name"] = row["name"]
    return m


# --- Messages ---------------------------------------------------------------

def append_messages(cid: str, messages: list[dict]) -> None:
    """Append messages to a conversation in order. Bumps updated_at."""
    if not messages:
        return
    now = time.time()
    with _db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM messages "
            "WHERE conversation_id=?",
            (cid,),
        ).fetchone()
        seq = (row["max_seq"] if row else 0) or 0
        for msg in messages:
            seq += 1
            tool_calls = msg.get("tool_calls")
            conn.execute(
                "INSERT INTO messages(conversation_id, seq, role, content, "
                "tool_calls_json, tool_call_id, name, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cid, seq,
                    msg.get("role", "user"),
                    msg.get("content", "") or "",
                    json.dumps(tool_calls) if tool_calls else None,
                    msg.get("tool_call_id"),
                    msg.get("name"),
                    now,
                ),
            )
        conn.execute(
            "UPDATE conversations SET updated_at=? WHERE id=?",
            (now, cid),
        )


def set_title_if_empty(cid: str, title: str) -> None:
    title = (title or "").strip()[:120]
    if not title:
        return
    with _db() as conn:
        conn.execute(
            "UPDATE conversations SET title=? "
            "WHERE id=? AND (title IS NULL OR title='')",
            (title, cid),
        )
