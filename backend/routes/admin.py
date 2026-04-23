"""Setup / admin endpoints: configure the source export path and run ingest.

Routes
------
GET  /api/admin/status         – is the DB ingested? row counts, source path, timestamps.
POST /api/admin/source         – { path: str } → validate + save the export path.
POST /api/admin/ingest         – run the pipeline. Streams progress as SSE.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db
from ..config import (
    DB_PATH,
    SCHEMA_JSON_PATH,
    get_source_dir,
    load_settings,
    save_settings,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# Guard: only one ingest at a time.
_ingest_lock = threading.Lock()


# ---------- status / source configuration ----------

@router.get("/status")
def status() -> dict:
    source = get_source_dir()
    settings = load_settings()
    out: dict = {
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "source_dir": str(source) if source else "",
        "source_env_override": bool(
            __import__("os").environ.get("MYCHART_SOURCE")
        ),
    }
    if DB_PATH.exists():
        try:
            stat = DB_PATH.stat()
            out["db_size_bytes"] = stat.st_size
            out["db_modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat(
                timespec="seconds"
            )
        except OSError:
            pass
        tables = db.ingested_tables()
        out["ingested_table_count"] = len(tables)
    out["last_ingest"] = settings.get("last_ingest", "")
    if source:
        out["source_info"] = _describe(source)
    return out


class SourceBody(BaseModel):
    path: str


@router.post("/source")
def set_source(body: SourceBody) -> dict:
    p = Path(body.path.strip()).expanduser()
    if not p.exists():
        raise HTTPException(400, f"Path does not exist: {p}")
    if not p.is_dir():
        raise HTTPException(400, f"Not a directory: {p}")
    info = _describe(p)
    settings = load_settings()
    settings["source_dir"] = str(p)
    save_settings(settings)
    return {"ok": True, "source_info": info}


@router.get("/validate")
def validate(path: str) -> dict:
    p = Path(path.strip()).expanduser()
    return _describe(p)


def _describe(source: Path) -> dict:
    """Quick summary for the UI — what's in this folder?"""
    from ingest.runner import describe_source

    return describe_source(source)


# ---------- ingestion (SSE stream) ----------

class IngestBody(BaseModel):
    skip_schema: bool = False
    skip_tsv: bool = False
    skip_fhir: bool = False
    skip_notes: bool = False
    # Optional override — otherwise uses the saved/env source.
    source: Optional[str] = None


@router.post("/ingest")
async def ingest(body: IngestBody):
    if _ingest_lock.locked():
        raise HTTPException(409, "Another ingest is already running.")

    if body.source:
        source = Path(body.source).expanduser()
    else:
        source = get_source_dir()
    if source is None:
        raise HTTPException(
            400,
            "No source export configured. POST /api/admin/source first.",
        )
    if not source.exists():
        raise HTTPException(400, f"Source path does not exist: {source}")

    from ingest.runner import IngestOptions, run_ingest

    opts = IngestOptions(
        source=source,
        db=DB_PATH,
        schema_json=SCHEMA_JSON_PATH,
        skip_schema=body.skip_schema,
        skip_tsv=body.skip_tsv,
        skip_fhir=body.skip_fhir,
        skip_notes=body.skip_notes,
    )

    q: "queue.Queue[dict | None]" = queue.Queue()

    def on_progress(evt: dict) -> None:
        q.put(evt)

    def worker() -> None:
        with _ingest_lock:
            try:
                result = run_ingest(opts, progress=on_progress)
                q.put({
                    "phase": "done",
                    "status": "ok" if result.ok else "error",
                    "message": result.message or "done",
                    "tables_loaded": result.tables_loaded,
                })
                # Persist last-ingest timestamp + source (in case caller overrode it).
                settings = load_settings()
                settings["last_ingest"] = datetime.now().isoformat(timespec="seconds")
                settings["source_dir"] = str(source)
                save_settings(settings)
                db.reset_caches()
            except Exception as e:  # noqa: BLE001
                q.put({"phase": "done", "status": "error", "message": str(e)})
            finally:
                q.put(None)  # sentinel

    threading.Thread(target=worker, daemon=True).start()

    async def event_stream():
        loop = asyncio.get_event_loop()
        # Heartbeat so the browser connection stays alive on long phases.
        yield "retry: 10000\n\n"
        while True:
            evt = await loop.run_in_executor(None, q.get)
            if evt is None:
                break
            yield f"data: {json.dumps(evt)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
