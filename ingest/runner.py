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

from . import assemble_notes, load_fhir, load_genome, load_tsv, parse_schema

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
    # 23andMe / genome integration. ``genome_source`` may point to either
    # a directory containing the export bundle or directly at the
    # ``genome_*.txt`` file. ``None`` => skip the genome phase entirely.
    genome_source: Optional[Path] = None
    skip_genome: bool = False
    skip_clinvar: bool = False


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
      {"phase": "schema"|"tsv"|"fhir"|"notes"|"genome"|"done",
       "status": "start"|"log"|"end",
       "message": "...", "value": int?, "total": int?}
    """
    src = opts.source.expanduser()
    # When the user only wants to (re-)ingest genome data, the Epic export
    # subfolders aren't required. We still run the rest of the pipeline if
    # they're present.
    epic_phases_skipped = (
        opts.skip_schema and opts.skip_tsv and opts.skip_fhir and opts.skip_notes
    )
    missing = check_source(src) if not epic_phases_skipped else []
    if missing and not epic_phases_skipped:
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
    schema_json: dict = {}
    if not (epic_phases_skipped and not schema_dir.exists()):
        t0 = time.time()
        if opts.skip_schema and opts.schema_json.exists():
            schema_json = json.loads(opts.schema_json.read_text(encoding="utf-8"))
            _emit(progress, phase="schema", status="end",
                  message=f"reusing {opts.schema_json.name} ({len(schema_json)} tables)")
        elif schema_dir.exists():
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
        if not opts.skip_tsv and tsv_dir.exists():
            t0 = time.time()
            _emit(progress, phase="tsv", status="start",
                  message=f"loading curated tables from {tsv_dir}")
            counts = load_tsv.load_all(conn, tsv_dir, schema_json)
            result.tables_loaded = counts
            _emit(progress, phase="tsv", status="end",
                  message=f"loaded {len(counts)} tables "
                          f"({sum(counts.values())} rows) in {time.time()-t0:.1f}s")

        # --- FHIR ---
        if not opts.skip_fhir and fhir_dir.exists():
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
            try:
                assemble_notes.assemble(conn)
                _emit(progress, phase="notes", status="end",
                      message=f"done in {time.time()-t0:.1f}s")
            except sqlite3.OperationalError as e:
                # Notes assembly depends on EHI tables — skip silently if
                # the user is only doing a genome-only re-ingest.
                _emit(progress, phase="notes", status="log",
                      message=f"skipped: {e}")

        # --- genome (23andMe + ClinVar) ---
        if not opts.skip_genome and opts.genome_source is not None:
            t0 = time.time()
            gsrc = opts.genome_source.expanduser()
            _emit(progress, phase="genome", status="start",
                  message=f"loading genome data from {gsrc}")
            try:
                gcounts = load_genome.load_all(
                    conn, gsrc,
                    clinvar_cache_dir=opts.db.parent / "clinvar",
                    skip_clinvar=opts.skip_clinvar,
                    progress=progress,
                )
                _emit(progress, phase="genome", status="end",
                      message=f"genome={gcounts['variants']:,} variants, "
                              f"ancestry={gcounts['ancestry']} segments, "
                              f"clinvar={gcounts['clinvar']:,} rows "
                              f"in {time.time()-t0:.1f}s")
            except Exception as e:  # noqa: BLE001
                _emit(progress, phase="genome", status="error",
                      message=f"genome load failed: {e}")

        conn.execute("PRAGMA optimize")
    finally:
        conn.close()

    _emit(progress, phase="done", status="end",
          message=f"DB -> {opts.db}")
    return result
