"""Thin SQLite wrapper opened read-only for API requests."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterable

from .config import DB_PATH, SCHEMA_JSON_PATH

_lock = threading.Lock()
_schema_cache: dict | None = None


def connect() -> sqlite3.Connection:
    # Open read-only (uri mode). If the DB file doesn't exist, surface a
    # clear error so the UI can prompt the user to run ingestion.
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. "
            "Run ingestion first (Setup page in the UI, or `python -m ingest --source ...`)."
        )
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def db_exists() -> bool:
    return DB_PATH.exists()


def reset_caches() -> None:
    """Drop memoized state. Call after a re-ingest."""
    global _schema_cache
    _schema_cache = None


@contextmanager
def cursor():
    conn = connect()
    try:
        yield conn.cursor()
    finally:
        conn.close()


def query(sql: str, params: Iterable = ()) -> list[dict]:
    with cursor() as cur:
        cur.execute(sql, tuple(params))
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def query_one(sql: str, params: Iterable = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def schema() -> dict:
    """Return parsed data-dictionary JSON produced during ingest."""
    global _schema_cache
    if _schema_cache is None:
        if SCHEMA_JSON_PATH.exists():
            _schema_cache = json.loads(
                SCHEMA_JSON_PATH.read_text(encoding="utf-8")
            )
        else:
            _schema_cache = {}
    return _schema_cache


def ingested_tables() -> list[str]:
    """All user tables currently in the DB (excluding system / fts shadow)."""
    if not DB_PATH.exists():
        return []
    with cursor() as cur:
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE '%_fts_%' "
            "ORDER BY name"
        )
        return [r[0] for r in cur.fetchall()]


def table_columns(name: str) -> list[str]:
    with cursor() as cur:
        cur.execute(f'PRAGMA table_info("{name}")')
        return [r[1] for r in cur.fetchall()]
