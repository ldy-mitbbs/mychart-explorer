"""Tools exposed to the LLM.

Each tool has:
  - a JSON-schema spec used for function-calling / tool-use.
  - a Python handler that takes **kwargs and returns a JSON-serialisable value.

Designed to be safe: SQL is funneled through `sql_guard`, note retrieval is
row-capped, and text results are size-capped to avoid blowing the context.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from .. import db, fhir
from ..sql_guard import UnsafeSQLError, ensure_safe


MAX_TEXT_CHARS = 8000
MAX_ROWS = 200


# --- Handlers ---------------------------------------------------------------

def _trunc(s: str, limit: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(s, str):
        return s
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n…[truncated {len(s)-limit} chars]"


def list_tables(**_: Any) -> dict:
    schema = db.schema()
    tables = db.ingested_tables()
    out = []
    for t in tables:
        entry = schema.get(t, {})
        out.append({
            "name": t,
            "description": entry.get("description", "")[:240],
        })
    return {"tables": out, "note":
            "These are the SQL tables you can query via run_sql. "
            "Use describe_table for columns."}


def describe_table(name: str, **_: Any) -> dict:
    entry = db.schema().get(name, {})
    cols_runtime = db.table_columns(name)
    col_meta = {c["name"]: c for c in entry.get("columns", [])}
    merged = []
    for c in cols_runtime:
        m = col_meta.get(c, {})
        merged.append({
            "name": c,
            "type": m.get("type", ""),
            "description": m.get("description", ""),
        })
    return {
        "name": name,
        "description": entry.get("description", ""),
        "primary_key": entry.get("primary_key", []),
        "columns": merged,
    }


def _schema_hint_for_error(query: str, err: str) -> dict:
    """Build a helpful hint when SQLite complains about a missing column/table.

    Extracts table names referenced in the query and returns their real
    column lists so the model can retry without another describe_table call.
    """
    hint: dict = {}
    # Tables mentioned in FROM / JOIN clauses (quoted or bare identifiers).
    table_names = re.findall(
        r'(?:from|join)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?',
        query, flags=re.IGNORECASE,
    )
    seen: set[str] = set()
    tables_info: dict[str, list[str]] = {}
    for t in table_names:
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        try:
            cols = db.table_columns(t)
        except Exception:
            cols = []
        if cols:
            tables_info[t] = cols
    if tables_info:
        hint["tables"] = tables_info
    # If the error names a missing column, surface close matches.
    m = re.search(r"no such column:\s*(\S+)", err)
    if m:
        bad = m.group(1).split(".")[-1].lower()
        suggestions: list[str] = []
        for cols in tables_info.values():
            for c in cols:
                cl = c.lower()
                if bad in cl or cl in bad:
                    suggestions.append(c)
        if suggestions:
            hint["did_you_mean"] = sorted(set(suggestions))[:10]
    return hint


def run_sql(query: str, max_rows: int = MAX_ROWS, **_: Any) -> dict:
    try:
        safe = ensure_safe(query, max_limit=min(max_rows, MAX_ROWS))
    except UnsafeSQLError as e:
        return {"error": str(e)}
    try:
        rows = db.query(safe)
    except Exception as e:
        err = f"SQL error: {e}"
        out: dict = {"error": err}
        hint = _schema_hint_for_error(query, str(e))
        if hint:
            out["hint"] = hint
            out["hint"]["note"] = (
                "Use the exact column names above. Call describe_table "
                "if you need descriptions."
            )
        return out
    return {"sql": safe, "row_count": len(rows), "rows": rows[:max_rows]}


def search_notes(q: str, limit: int = 20, **_: Any) -> dict:
    match = db.fts_query(q)
    if not match:
        return {"notes": [], "messages": [], "hint": "empty query after sanitization"}
    lim = max(1, min(limit, 50))
    rows = db.query(
        "SELECT n.note_id, n.description, n.note_type, n.author, n.created, "
        "n.pat_enc_csn, "
        "snippet(notes_fts, 2, '<<', '>>', '…', 20) AS snippet "
        "FROM notes_fts f JOIN notes_assembled n ON n.note_id = f.note_id "
        "WHERE notes_fts MATCH ? ORDER BY rank LIMIT ?",
        (match, lim),
    )
    msgs = db.query(
        "SELECT m.msg_id, m.sent, m.from_user, m.subject, "
        "snippet(messages_fts, 2, '<<', '>>', '…', 20) AS snippet "
        "FROM messages_fts f JOIN messages_assembled m ON m.msg_id = f.msg_id "
        "WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?",
        (match, lim),
    )
    return {"notes": rows, "messages": msgs, "match": match}


def get_note(note_id: str, **_: Any) -> dict:
    row = db.query_one(
        "SELECT * FROM notes_assembled WHERE note_id=?", (note_id,)
    )
    if not row:
        return {"error": "note not found"}
    row = dict(row)
    row["full_text"] = _trunc(row.get("full_text", "") or "")
    return row


def get_message(msg_id: str, **_: Any) -> dict:
    row = db.query_one(
        "SELECT * FROM messages_assembled WHERE msg_id=?", (msg_id,)
    )
    if not row:
        return {"error": "message not found"}
    row = dict(row)
    row["body"] = _trunc(row.get("body", "") or "")
    return row


def lab_trend(component: str, **_: Any) -> dict:
    select_cols = (
        'SELECT RESULT_DATE AS time, ORD_VALUE AS raw_value, '
        'ORD_NUM_VALUE AS value, REFERENCE_LOW AS ref_low, '
        'REFERENCE_HIGH AS ref_high, REFERENCE_UNIT AS unit, '
        'RESULT_FLAG_C_NAME AS flag, COMPONENT_ID_NAME AS component '
        'FROM "ORDER_RESULTS" '
    )
    rows = db.query(
        select_cols + 'WHERE COMPONENT_ID_NAME=? ORDER BY RESULT_DATE',
        (component,),
    )
    matched = component
    if not rows:
        # Fallback: case-insensitive LIKE so the model doesn't need the
        # exact component name.
        rows = db.query(
            select_cols
            + 'WHERE COMPONENT_ID_NAME LIKE ? ORDER BY RESULT_DATE',
            (f"%{component}%",),
        )
        if rows:
            matched = sorted({r["component"] for r in rows if r.get("component")})
    if not rows:
        # Offer candidates so the model can retry with a valid name.
        candidates = db.query(
            'SELECT DISTINCT COMPONENT_ID_NAME AS name '
            'FROM "ORDER_RESULTS" WHERE COMPONENT_ID_NAME LIKE ? '
            'ORDER BY name LIMIT 20',
            (f"%{component}%",),
        )
        return {
            "component": component,
            "points": [],
            "count": 0,
            "candidates": [c["name"] for c in candidates],
            "hint": "No exact or substring match. Try one of the candidates "
                    "or run_sql against ORDER_RESULTS directly.",
        }
    return {
        "component": component,
        "matched_components": matched,
        "points": rows,
        "count": len(rows),
    }


_VITAL_SUMMARY_NAMES = (
    "BLOOD PRESSURE", "PULSE", "TEMPERATURE", "RESPIRATIONS",
    "PULSE OXIMETRY", "WEIGHT/SCALE", "HEIGHT", "BMI",
    "R ENGLISH WEIGHT LBS",
)


def _numeric(value: str) -> float | None:
    if value is None:
        return None
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(value))
    return float(m.group(1)) if m else None


def _split_bp(value: str) -> tuple[float | None, float | None]:
    """Parse '118/72' into (systolic, diastolic). Returns (None, None) if unparseable."""
    if not value:
        return None, None
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)", str(value))
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def vitals_trend(name: str, **_: Any) -> dict:
    """Time series for a flowsheet vital (BP, pulse, temp, weight, etc.).

    Values live in V_EHI_FLO_MEAS_VALUE joined to IP_FLWSHT_MEAS by
    (FSD_ID, LINE). Accepts a substring; returns candidate names if
    nothing matches.
    """
    select_cols = (
        'SELECT m.RECORDED_TIME AS time, v.MEAS_VALUE_EXTERNAL AS raw_value, '
        'v.UNITS AS unit, v.FLO_MEAS_ID_FLO_MEAS_NAME AS measurement '
        'FROM "V_EHI_FLO_MEAS_VALUE" v '
        'LEFT JOIN "IP_FLWSHT_MEAS" m USING (FSD_ID, LINE) '
    )
    rows = db.query(
        select_cols
        + 'WHERE v.FLO_MEAS_ID_FLO_MEAS_NAME=? '
          'AND v.MEAS_VALUE_EXTERNAL IS NOT NULL AND v.MEAS_VALUE_EXTERNAL <> "" '
          'ORDER BY m.RECORDED_TIME',
        (name,),
    )
    matched: Any = name
    if not rows:
        rows = db.query(
            select_cols
            + 'WHERE v.FLO_MEAS_ID_FLO_MEAS_NAME LIKE ? '
              'AND v.MEAS_VALUE_EXTERNAL IS NOT NULL AND v.MEAS_VALUE_EXTERNAL <> "" '
              'ORDER BY m.RECORDED_TIME',
            (f"%{name.upper()}%",),
        )
        if rows:
            matched = sorted({r["measurement"] for r in rows if r.get("measurement")})
    if not rows:
        candidates = db.query(
            'SELECT DISTINCT FLO_MEAS_ID_FLO_MEAS_NAME AS name '
            'FROM "V_EHI_FLO_MEAS_VALUE" '
            'WHERE FLO_MEAS_ID_FLO_MEAS_NAME LIKE ? '
            'AND MEAS_VALUE_EXTERNAL IS NOT NULL AND MEAS_VALUE_EXTERNAL <> "" '
            'ORDER BY name LIMIT 20',
            (f"%{name.upper()}%",),
        )
        return {
            "measurement": name,
            "points": [],
            "count": 0,
            "candidates": [c["name"] for c in candidates],
            "hint": "No exact or substring match. Try a candidate or browse "
                    "V_EHI_FLO_MEAS_VALUE via run_sql.",
        }
    is_bp = any(
        "BLOOD PRESSURE" in (r.get("measurement") or "") for r in rows
    )
    for r in rows:
        raw = r.get("raw_value")
        if is_bp:
            sys_, dia = _split_bp(raw)
            r["systolic"] = sys_
            r["diastolic"] = dia
        else:
            r["value"] = _numeric(raw)
    return {
        "measurement": name,
        "matched_measurements": matched,
        "is_blood_pressure": is_bp,
        "points": rows[:MAX_ROWS],
        "count": len(rows),
    }


def _recent_vitals() -> list[dict]:
    """Latest value for a short list of interesting vitals. Best-effort."""
    placeholders = ",".join("?" * len(_VITAL_SUMMARY_NAMES))
    try:
        return db.query(
            'SELECT v.FLO_MEAS_ID_FLO_MEAS_NAME AS name, '
            'v.MEAS_VALUE_EXTERNAL AS value, v.UNITS AS unit, '
            'm.RECORDED_TIME AS time '
            'FROM "V_EHI_FLO_MEAS_VALUE" v '
            'LEFT JOIN "IP_FLWSHT_MEAS" m USING (FSD_ID, LINE) '
            'WHERE v.FLO_MEAS_ID_FLO_MEAS_NAME IN (' + placeholders + ') '
            'AND v.MEAS_VALUE_EXTERNAL IS NOT NULL '
            'AND v.MEAS_VALUE_EXTERNAL <> "" '
            'AND m.RECORDED_TIME IS NOT NULL '
            'AND (v.FLO_MEAS_ID_FLO_MEAS_NAME, m.RECORDED_TIME) IN ('
            '  SELECT v2.FLO_MEAS_ID_FLO_MEAS_NAME, MAX(m2.RECORDED_TIME) '
            '  FROM "V_EHI_FLO_MEAS_VALUE" v2 '
            '  LEFT JOIN "IP_FLWSHT_MEAS" m2 USING (FSD_ID, LINE) '
            '  WHERE v2.MEAS_VALUE_EXTERNAL IS NOT NULL '
            '  AND v2.MEAS_VALUE_EXTERNAL <> "" '
            '  GROUP BY v2.FLO_MEAS_ID_FLO_MEAS_NAME'
            ') '
            'ORDER BY m.RECORDED_TIME DESC',
            tuple(_VITAL_SUMMARY_NAMES),
        )
    except Exception:
        return []


def get_patient_summary(**_: Any) -> dict:
    p = fhir.patient_summary()
    problems = fhir.conditions()
    allergies = fhir.allergies()
    meds = fhir.medications()[:25]
    recent_encounters = fhir.encounters()[:10]
    return {
        "patient": {k: p.get(k) for k in
                    ("name", "birthDate", "gender", "mrn", "address")},
        "active_problems": [
            c for c in problems
            if (c.get("clinicalStatus") or "").lower() == "active"
        ][:30],
        "allergies": allergies,
        "recent_medications": meds,
        "recent_encounters": recent_encounters,
        "recent_vitals": _recent_vitals(),
    }


# --- Registry ---------------------------------------------------------------

ToolHandler = Callable[..., Any]


TOOLS: dict[str, tuple[ToolHandler, dict]] = {
    "list_tables": (list_tables, {
        "type": "object", "properties": {}, "additionalProperties": False,
    }),
    "describe_table": (describe_table, {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }),
    "run_sql": (run_sql, {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A single read-only SQLite SELECT. "
                               "A LIMIT will be enforced.",
            },
            "max_rows": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        "required": ["query"],
    }),
    "search_notes": (search_notes, {
        "type": "object",
        "properties": {
            "q": {"type": "string",
                  "description": "FTS5 MATCH query over clinical notes AND "
                                 "MyChart messages."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["q"],
    }),
    "get_note": (get_note, {
        "type": "object",
        "properties": {"note_id": {"type": "string"}},
        "required": ["note_id"],
    }),
    "get_message": (get_message, {
        "type": "object",
        "properties": {"msg_id": {"type": "string"}},
        "required": ["msg_id"],
    }),
    "lab_trend": (lab_trend, {
        "type": "object",
        "properties": {
            "component": {
                "type": "string",
                "description": "Exact lab component name from ORDER_RESULTS "
                               "(e.g. 'HEMOGLOBIN A1C').",
            },
        },
        "required": ["component"],
    }),
    "vitals_trend": (vitals_trend, {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Flowsheet measurement name or substring "
                               "(e.g. 'BLOOD PRESSURE', 'PULSE', 'WEIGHT'). "
                               "Case-insensitive substring match is supported.",
            },
        },
        "required": ["name"],
    }),
    "get_patient_summary": (get_patient_summary, {
        "type": "object", "properties": {}, "additionalProperties": False,
    }),
}


TOOL_DESCRIPTIONS: dict[str, str] = {
    "list_tables": "List the patient's clinical SQL tables and their "
                   "descriptions.",
    "describe_table":
        "Return a table's columns and their descriptions.",
    "run_sql":
        "Run a read-only SELECT against the patient's SQLite database. "
        "Returns rows (capped). Use this for structured queries.",
    "search_notes":
        "Full-text search over clinical notes and MyChart messages. "
        "Returns note/message IDs + snippets. Use get_note / get_message "
        "to read a full document.",
    "get_note": "Fetch the full assembled text of a clinical note.",
    "get_message": "Fetch the full body of a MyChart message.",
    "lab_trend":
        "Return the time series for a named lab component (e.g. 'HbA1c'). "
        "Useful for trend questions.",
    "vitals_trend":
        "Return the time series for a flowsheet vital sign by name "
        "(e.g. 'BLOOD PRESSURE', 'PULSE', 'TEMPERATURE', 'WEIGHT'). "
        "For BLOOD PRESSURE each point includes split systolic/diastolic. "
        "Use this instead of run_sql for any vitals question.",
    "get_patient_summary":
        "Return a precomputed summary: demographics, active problems, "
        "allergies, recent medications, recent encounters. Good default "
        "context for open-ended questions.",
}


def tool_specs(style: str = "openai") -> list[dict]:
    """Return tool specs in provider-specific shape.

    Ollama + OpenAI both accept the OpenAI "tools" array. Anthropic's shape
    is converted inside the provider.
    """
    specs = []
    for name, (_, params) in TOOLS.items():
        specs.append({
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS.get(name, ""),
                "parameters": params,
            },
        })
    return specs


def dispatch(name: str, arguments: dict) -> str:
    """Run the tool and return a JSON string for the LLM."""
    if name not in TOOLS:
        return json.dumps({"error": f"unknown tool: {name}"})
    handler, _ = TOOLS[name]
    try:
        result = handler(**(arguments or {}))
    except TypeError as e:
        return json.dumps({"error": f"bad arguments: {e}"})
    except Exception as e:  # pragma: no cover — runtime safety net
        return json.dumps({"error": f"{type(e).__name__}: {e}"})
    try:
        return json.dumps(result, default=str)[:20000]
    except Exception as e:
        return json.dumps({"error": f"serialisation failed: {e}"})
