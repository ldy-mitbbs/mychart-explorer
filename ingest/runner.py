"""Library entrypoint for running an ingest.

This module wraps the phase-by-phase logic that lived in ``__main__.py`` so
it can be called both from the CLI and from the backend (which streams
progress to the UI while a user kicks off an ingest).
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import assemble_notes, load_fhir, load_tsv, parse_schema

ProgressFn = Callable[[dict], None]


@dataclass
class IngestOptions:
    source: Path
    db: Path
    schema_json: Path
    skip_schema: bool = False
    skip_tsv: bool = False
    skip_fhir: bool = False
    skip_notes: bool = False


@dataclass
class IngestResult:
    ok: bool
    db: Path
    tables_loaded: dict[str, int] = field(default_factory=dict)
    message: str = ""


def _emit(cb: Optional[ProgressFn], **kw) -> None:
    if cb:
        try:
            cb(kw)
        except Exception:
            pass


def check_source(source: Path) -> list[str]:
    """Return a list of missing required subfolders. Empty list means OK."""
    required = ["EHITables", "EHITables Schema", "FHIR"]
    return [sub for sub in required if not (source / sub).exists()]


def describe_source(source: Path) -> dict:
    """Quick summary for the UI — what's in this folder?"""
    info: dict = {"source": str(source), "exists": source.exists()}
    if not source.exists():
        return info
    tsv_dir = source / "EHITables"
    schema_dir = source / "EHITables Schema"
    fhir_dir = source / "FHIR"
    info["has_ehi_tables"] = tsv_dir.exists()
    info["has_ehi_schema"] = schema_dir.exists()
    info["has_fhir"] = fhir_dir.exists()
    info["missing"] = check_source(source)
    if tsv_dir.exists():
        info["tsv_count"] = sum(1 for _ in tsv_dir.glob("*.tsv"))
    if schema_dir.exists():
        info["schema_htm_count"] = sum(1 for _ in schema_dir.glob("*.htm"))
    if fhir_dir.exists():
        info["fhir_file_count"] = sum(
            1 for p in fhir_dir.iterdir() if p.suffix.lower() == ".ndjson"
        )
    return info


def run_ingest(opts: IngestOptions, progress: Optional[ProgressFn] = None) -> IngestResult:
    """Run the full ingest pipeline. Yields progress dicts through ``progress``.

    Progress shapes:
      {"phase": "schema"|"tsv"|"fhir"|"notes"|"done", "status": "start"|"log"|"end",
       "message": "...", "value": int?, "total": int?}
    """
    src = opts.source.expanduser()
    missing = check_source(src)
    if missing:
        msg = "Missing required subfolders: " + ", ".join(missing)
        _emit(progress, phase="done", status="error", message=msg)
        return IngestResult(ok=False, db=opts.db, message=msg)

    tsv_dir = src / "EHITables"
    schema_dir = src / "EHITables Schema"
    fhir_dir = src / "FHIR"

    opts.db.parent.mkdir(parents=True, exist_ok=True)
    opts.schema_json.parent.mkdir(parents=True, exist_ok=True)

    result = IngestResult(ok=True, db=opts.db)

    # --- schema.json ---
    t0 = time.time()
    if opts.skip_schema and opts.schema_json.exists():
        schema_json = json.loads(opts.schema_json.read_text(encoding="utf-8"))
        _emit(progress, phase="schema", status="end",
              message=f"reusing {opts.schema_json.name} ({len(schema_json)} tables)")
    else:
        _emit(progress, phase="schema", status="start",
              message=f"parsing {schema_dir}")
        n = parse_schema.write_schema_json(schema_dir, opts.schema_json)
        schema_json = json.loads(opts.schema_json.read_text(encoding="utf-8"))
        _emit(progress, phase="schema", status="end",
              message=f"parsed {n} tables in {time.time()-t0:.1f}s")

    conn = sqlite3.connect(opts.db)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        # --- curated TSVs ---
        if not opts.skip_tsv:
            t0 = time.time()
            _emit(progress, phase="tsv", status="start",
                  message=f"loading curated tables from {tsv_dir}")
            counts = load_tsv.load_all(conn, tsv_dir, schema_json)
            result.tables_loaded = counts
            _emit(progress, phase="tsv", status="end",
                  message=f"loaded {len(counts)} tables "
                          f"({sum(counts.values())} rows) in {time.time()-t0:.1f}s")

        # --- FHIR ---
        if not opts.skip_fhir:
            t0 = time.time()
            _emit(progress, phase="fhir", status="start",
                  message=f"loading {fhir_dir}")
            load_fhir.load_all(conn, fhir_dir)
            _emit(progress, phase="fhir", status="end",
                  message=f"done in {time.time()-t0:.1f}s")

        # --- notes ---
        if not opts.skip_notes:
            t0 = time.time()
            _emit(progress, phase="notes", status="start",
                  message="assembling notes + messages + FTS")
            assemble_notes.assemble(conn)
            _emit(progress, phase="notes", status="end",
                  message=f"done in {time.time()-t0:.1f}s")

        conn.execute("PRAGMA optimize")
    finally:
        conn.close()

    _emit(progress, phase="done", status="end",
          message=f"DB -> {opts.db}")
    return result
