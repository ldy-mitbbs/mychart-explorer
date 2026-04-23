"""Load FHIR NDJSON exports into SQLite.

Two tables:
  fhir_resources(resource_type TEXT, id TEXT, json TEXT, PRIMARY KEY(rt,id))
  fhir_binaries(id TEXT PRIMARY KEY, content_type TEXT, text TEXT)

Plus lightweight flat views for common resource types via Python helpers so
the frontend & LLM tools can query without parsing JSON every time.
"""

from __future__ import annotations

import base64
import json
import re
import sqlite3
from pathlib import Path


RESOURCE_TYPE_FROM_FILENAME = re.compile(r"^([A-Za-z]+)\d*\.NDJSON$")


def _resource_type_from_name(fname: str) -> str:
    m = RESOURCE_TYPE_FROM_FILENAME.match(fname)
    if m:
        return m.group(1).capitalize().replace(
            "Allergyintolerance", "AllergyIntolerance"
        ).replace(
            "Careplan", "CarePlan"
        ).replace(
            "Careteam", "CareTeam"
        ).replace(
            "Diagnosticreport", "DiagnosticReport"
        ).replace(
            "Documentreference", "DocumentReference"
        ).replace(
            "Medicationrequest", "MedicationRequest"
        )
    return fname


def init_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS fhir_resources;
        CREATE TABLE fhir_resources (
            resource_type TEXT NOT NULL,
            id            TEXT NOT NULL,
            json          TEXT NOT NULL,
            PRIMARY KEY (resource_type, id)
        );
        CREATE INDEX idx_fhir_rt ON fhir_resources(resource_type);

        DROP TABLE IF EXISTS fhir_binaries;
        CREATE TABLE fhir_binaries (
            id           TEXT PRIMARY KEY,
            content_type TEXT,
            text         TEXT
        );
        """
    )
    conn.commit()


def _decode_binary(res: dict) -> tuple[str, str]:
    ct = res.get("contentType") or ""
    data = res.get("data") or ""
    if not data:
        return ct, ""
    try:
        raw = base64.b64decode(data, validate=False)
    except Exception:
        return ct, ""
    # Try common encodings; Epic binaries are usually RTF or HTML.
    for enc in ("utf-8", "latin-1"):
        try:
            return ct, raw.decode(enc, errors="replace")
        except Exception:
            continue
    return ct, ""


def load_all(conn: sqlite3.Connection, fhir_dir: Path, log=print) -> dict[str, int]:
    init_schema(conn)
    cur = conn.cursor()
    counts: dict[str, int] = {}

    for path in sorted(fhir_dir.glob("*.NDJSON")):
        rt_guess = _resource_type_from_name(path.name)
        batch: list[tuple] = []
        bin_batch: list[tuple] = []
        n = 0
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    res = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rt = res.get("resourceType") or rt_guess
                rid = res.get("id") or ""
                batch.append((rt, rid, line))
                if rt == "Binary":
                    ct, txt = _decode_binary(res)
                    bin_batch.append((rid, ct, txt))
                if len(batch) >= 1000:
                    cur.executemany(
                        "INSERT OR REPLACE INTO fhir_resources VALUES (?,?,?)",
                        batch,
                    )
                    n += len(batch)
                    batch.clear()
                if len(bin_batch) >= 200:
                    cur.executemany(
                        "INSERT OR REPLACE INTO fhir_binaries VALUES (?,?,?)",
                        bin_batch,
                    )
                    bin_batch.clear()
        if batch:
            cur.executemany(
                "INSERT OR REPLACE INTO fhir_resources VALUES (?,?,?)", batch
            )
            n += len(batch)
        if bin_batch:
            cur.executemany(
                "INSERT OR REPLACE INTO fhir_binaries VALUES (?,?,?)", bin_batch
            )
        conn.commit()
        counts[path.name] = n
        log(f"  loaded {path.name}: {n} resources")
    return counts
