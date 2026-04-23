"""Load curated EHI TSVs into SQLite.

- Column types are taken from the parsed schema; unknown types fall back to
  TEXT so we never lose data.
- DATETIME columns are normalised to ISO 8601 strings for sortability.
- NUMERIC columns are stored as REAL (with TEXT fallback on parse error so
  values like a 7-digit MRN don't get silently coerced to a lossy float).
- One index per `INDEX_COLUMNS` present in the table.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .tables import CURATED_TABLES, INDEX_COLUMNS

# Raise csv field size limit — some Epic note/text columns are huge.
csv.field_size_limit(1 << 24)

_DT_FORMATS = (
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def _parse_dt(value: str) -> str | None:
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(v, fmt).isoformat(sep=" ")
        except ValueError:
            continue
    return v  # unrecognised — keep raw so the UI can still display it


def _parse_num(value: str):
    if value is None or value == "":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value  # keep raw rather than drop


_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Unsafe identifier: {name!r}")
    return name


def _coltype_for(col_type: str) -> str:
    t = (col_type or "").upper()
    if "NUMERIC" in t:
        return "NUMERIC"  # SQLite affinity — accepts int/float/text
    if "DATETIME" in t or "DATE" in t:
        return "TEXT"
    return "TEXT"


def load_table(
    conn: sqlite3.Connection,
    tsv_path: Path,
    table_name: str,
    schema: dict | None,
) -> int:
    """Load one TSV into SQLite. Returns row count inserted."""
    _safe_ident(table_name)

    with tsv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            header = next(reader)
        except StopIteration:
            return 0

        # Dedupe/validate column names.
        cols = [_safe_ident(h.strip()) for h in header]
        col_types_by_name: dict[str, str] = {}
        if schema:
            for c in schema.get("columns", []):
                col_types_by_name[c["name"]] = c["type"]

        sqlite_types = [_coltype_for(col_types_by_name.get(c, "")) for c in cols]
        # Flag which columns need datetime / numeric parsing.
        is_dt = [
            "DATETIME" in (col_types_by_name.get(c, "") or "").upper()
            or "DATE" in (col_types_by_name.get(c, "") or "").upper()
            for c in cols
        ]
        is_num = [
            "NUMERIC" in (col_types_by_name.get(c, "") or "").upper()
            for c in cols
        ]

        cur = conn.cursor()
        cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        col_defs = ", ".join(
            f'"{c}" {t}' for c, t in zip(cols, sqlite_types)
        )
        cur.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

        placeholders = ", ".join("?" * len(cols))
        insert_sql = (
            f'INSERT INTO "{table_name}" '
            f'({", ".join(chr(34) + c + chr(34) for c in cols)}) '
            f'VALUES ({placeholders})'
        )

        batch: list[tuple] = []
        count = 0
        BATCH = 5000
        for row in reader:
            # Pad/truncate to header width.
            if len(row) < len(cols):
                row = row + [""] * (len(cols) - len(row))
            elif len(row) > len(cols):
                row = row[: len(cols)]
            converted = []
            for i, v in enumerate(row):
                if is_dt[i]:
                    converted.append(_parse_dt(v))
                elif is_num[i]:
                    converted.append(_parse_num(v))
                else:
                    converted.append(v if v != "" else None)
            batch.append(tuple(converted))
            if len(batch) >= BATCH:
                cur.executemany(insert_sql, batch)
                count += len(batch)
                batch.clear()
        if batch:
            cur.executemany(insert_sql, batch)
            count += len(batch)

        # Indexes on useful columns.
        for col in cols:
            if col in INDEX_COLUMNS:
                idx = f"idx_{table_name}_{col}"
                cur.execute(
                    f'CREATE INDEX IF NOT EXISTS "{idx}" '
                    f'ON "{table_name}" ("{col}")'
                )

        conn.commit()
        return count


def load_all(
    conn: sqlite3.Connection,
    tsv_dir: Path,
    schema_json: dict[str, dict],
    tables: Iterable[str] = CURATED_TABLES,
    log=print,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in tables:
        path = tsv_dir / f"{name}.tsv"
        if not path.exists():
            log(f"  skip (missing): {name}")
            continue
        try:
            n = load_table(conn, path, name, schema_json.get(name))
            counts[name] = n
            log(f"  loaded {name}: {n} rows")
        except Exception as e:
            log(f"  ERROR {name}: {e}")
    return counts
