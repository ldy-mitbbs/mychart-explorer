"""Generic table browser and read-only SQL endpoint."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import db
from ..config import get_source_dir
from ..sql_guard import UnsafeSQLError, ensure_safe

router = APIRouter()


@router.get("/tables")
def list_tables() -> dict:
    """Return every ingested table + metadata from the parsed data dictionary.

    Tables not yet ingested but present as a TSV on disk are returned under
    `available` so the UI can still let you peek at them via `/tables/{name}`.
    """
    ingested = set(db.ingested_tables())
    schema = db.schema()

    def meta(name: str) -> dict:
        entry = schema.get(name, {})
        return {
            "name": name,
            "description": entry.get("description", ""),
            "primary_key": entry.get("primary_key", []),
            "column_count": len(entry.get("columns", [])),
            "ingested": name in ingested,
        }

    # Anything on disk (if the user has configured a source export).
    source = get_source_dir()
    tsv_dir = source / "EHITables" if source else None
    on_disk = (
        sorted(p.stem for p in tsv_dir.glob("*.tsv"))
        if tsv_dir and tsv_dir.exists() else []
    )
    all_names = sorted(set(on_disk) | ingested | set(schema.keys()))
    return {"tables": [meta(n) for n in all_names]}


@router.get("/tables/{name}")
def show_table(
    name: str,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = 0,
    q: str | None = None,
) -> dict:
    """Read rows from a table.

    If the table is ingested, we query SQLite (fast, filterable).
    Otherwise we stream the TSV from disk (headers + first N rows).
    """
    # Safety: only allow simple identifiers.
    if not name.replace("_", "").isalnum():
        raise HTTPException(400, "Invalid table name.")

    if name in db.ingested_tables():
        cols = db.table_columns(name)
        where = ""
        params: list = []
        if q:
            clauses = " OR ".join(f'"{c}" LIKE ?' for c in cols)
            where = f" WHERE {clauses}"
            params = [f"%{q}%"] * len(cols)
        total = db.query_one(
            f'SELECT COUNT(*) AS n FROM "{name}"{where}', params
        ) or {"n": 0}
        rows = db.query(
            f'SELECT * FROM "{name}"{where} LIMIT ? OFFSET ?',
            [*params, limit, offset],
        )
        schema = db.schema().get(name, {})
        return {
            "name": name, "columns": cols, "rows": rows,
            "total": total["n"], "limit": limit, "offset": offset,
            "description": schema.get("description", ""),
            "column_meta": schema.get("columns", []),
            "source": "sqlite",
        }

    # Fall back to TSV on disk.
    source = get_source_dir()
    if source is None:
        raise HTTPException(404, f"Table not in DB and no source export configured: {name}")
    tsv = source / "EHITables" / f"{name}.tsv"
    if not tsv.exists():
        raise HTTPException(404, f"Table not found: {name}")
    with tsv.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            header = next(reader)
        except StopIteration:
            return {"name": name, "columns": [], "rows": [], "total": 0,
                    "limit": limit, "offset": offset, "source": "tsv"}
        rows_out: list[dict] = []
        skipped = 0
        needle = q.lower() if q else None
        for row in reader:
            if needle and not any(needle in cell.lower() for cell in row):
                continue
            if skipped < offset:
                skipped += 1
                continue
            if len(rows_out) >= limit:
                break
            rows_out.append(dict(zip(header, row)))
        schema = db.schema().get(name, {})
        return {
            "name": name, "columns": list(header), "rows": rows_out,
            "total": None,  # unknown without scanning whole file
            "limit": limit, "offset": offset,
            "description": schema.get("description", ""),
            "column_meta": schema.get("columns", []),
            "source": "tsv",
        }


# --- SQL passthrough --------------------------------------------------------

class SqlRequest(BaseModel):
    sql: str
    max_rows: int = 500


@router.post("/sql")
def run_sql(req: SqlRequest) -> dict:
    try:
        safe = ensure_safe(req.sql, max_limit=min(req.max_rows, 5000))
    except UnsafeSQLError as e:
        raise HTTPException(400, str(e))
    try:
        rows = db.query(safe)
    except sqlite3.OperationalError as e:
        raise HTTPException(400, f"SQL error: {e}")
    cols = list(rows[0].keys()) if rows else []
    return {"sql": safe, "columns": cols, "rows": rows, "count": len(rows)}
