"""Patient-facing clinical data routes.

These are deliberately thin wrappers over the flattened FHIR helpers, with a
couple of endpoints that fall back to EHI tables when the FHIR data is sparse
(e.g. allergies in this export).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import db, fhir

router = APIRouter()


@router.get("/patient")
def get_patient() -> dict:
    summary = fhir.patient_summary()
    # Augment with a few fields from the PATIENT table if present.
    try:
        row = db.query_one('SELECT * FROM "PATIENT" LIMIT 1')
    except Exception:
        row = None
    if row:
        summary.setdefault("patTable", dict(row))
    try:
        row2 = db.query_one('SELECT * FROM "PATIENT_2" LIMIT 1')
        if row2:
            summary["patTable2"] = dict(row2)
    except Exception:
        pass
    return summary


@router.get("/problems")
def get_problems() -> list[dict]:
    # Prefer EHI PROBLEM_LIST because it has stage/priority/chronic flags,
    # fall back to FHIR Condition.
    try:
        rows = db.query(
            'SELECT PROBLEM_LIST_ID, DX_ID_DX_NAME, DESCRIPTION, NOTED_DATE, '
            'RESOLVED_DATE, DATE_OF_ENTRY, PROBLEM_STATUS_C_NAME, '
            'CLASS_OF_PROBLEM_C_NAME, CHRONIC_YN, PRIORITY_C_NAME '
            'FROM "PROBLEM_LIST" ORDER BY NOTED_DATE DESC'
        )
        if rows:
            return rows
    except Exception:
        pass
    return fhir.conditions()


@router.get("/allergies")
def get_allergies() -> list[dict]:
    try:
        rows = db.query(
            'SELECT a.ALLERGY_ID, a.ALLERGEN_ID_ALLERGEN_NAME AS allergen, '
            'a.REACTION, a.DATE_NOTED, a.SEVERITY_C_NAME AS severity, '
            'a.ALLERGY_SEVERITY_C_NAME AS allergy_severity, '
            'a.ALRGY_STATUS_C_NAME AS status '
            'FROM "ALLERGY" a'
        )
        # Attach structured reactions.
        if rows:
            for r in rows:
                try:
                    extra = db.query(
                        'SELECT * FROM "ALLERGY_REACTIONS" WHERE ALLERGY_ID=?',
                        (r["ALLERGY_ID"],),
                    )
                    r["structured_reactions"] = extra
                except Exception:
                    pass
            return rows
    except Exception:
        pass
    return fhir.allergies()


@router.get("/medications")
def get_medications(active: bool | None = None) -> list[dict]:
    # Build from EHI ORDER_MED for richer fields.
    try:
        rows = db.query(
            'SELECT ORDER_MED_ID, MEDICATION_ID_MEDICATION_NAME AS medication, '
            'DOSAGE, QUANTITY, REFILLS, START_DATE, END_DATE, '
            'ORDERING_DATE, PAT_ENC_CSN_ID, '
            'MED_PRESC_PROV_ID_PROV_NAME AS prescriber, '
            'PHARMACY_ID_PHARMACY_NAME AS pharmacy, '
            'ORDER_CLASS_C_NAME AS order_class, '
            'RSN_FOR_DISCON_C_NAME AS discontinue_reason, '
            'DESCRIPTION '
            'FROM "ORDER_MED" ORDER BY ORDERING_DATE DESC'
        )
        if rows:
            if active is not None:
                rows = [
                    r for r in rows
                    if (r.get("discontinue_reason") in (None, ""))
                    == bool(active)
                ]
            return rows
    except Exception:
        pass
    return fhir.medications()


@router.get("/immunizations")
def get_immunizations() -> list[dict]:
    return fhir.immunizations()


@router.get("/procedures")
def get_procedures() -> list[dict]:
    return fhir.procedures()


@router.get("/history/{hx_type}")
def get_history(hx_type: str) -> list[dict]:
    table_map = {
        "medical": "MEDICAL_HX",
        "surgical": "SURGICAL_HX",
        "family": "FAMILY_HX",
        "social": "SOCIAL_HX",
    }
    tbl = table_map.get(hx_type.lower())
    if not tbl:
        raise HTTPException(404, f"Unknown history type: {hx_type}")
    try:
        return db.query(f'SELECT * FROM "{tbl}"')
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/encounters")
def get_encounters(
    q: str | None = Query(None, description="Filter by dept / provider"),
    limit: int = 500,
) -> list[dict]:
    sql = (
        'SELECT e.PAT_ENC_CSN_ID AS csn, e.CONTACT_DATE, '
        'e.VISIT_PROV_ID_PROV_NAME AS provider, '
        'e.DEPARTMENT_ID_EXTERNAL_NAME AS department, '
        'e.APPT_STATUS_C_NAME AS status, '
        'e.PCP_PROV_ID_PROV_NAME AS pcp, '
        'e2.PHYS_BP AS bp, e2.PHYS_SPO2 AS spo2 '
        'FROM "PAT_ENC" e '
        'LEFT JOIN "PAT_ENC_2" e2 USING (PAT_ENC_CSN_ID) '
    )
    params: list = []
    if q:
        sql += (
            "WHERE e.VISIT_PROV_ID_PROV_NAME LIKE ? "
            "OR e.DEPARTMENT_ID_EXTERNAL_NAME LIKE ? "
        )
        like = f"%{q}%"
        params = [like, like]
    sql += "ORDER BY e.CONTACT_DATE DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)


@router.get("/encounters/{csn}")
def get_encounter(csn: str) -> dict:
    enc = db.query_one(
        'SELECT * FROM "PAT_ENC" WHERE CAST(PAT_ENC_CSN_ID AS TEXT)=?', (csn,)
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")
    enc2 = db.query_one(
        'SELECT * FROM "PAT_ENC_2" WHERE CAST(PAT_ENC_CSN_ID AS TEXT)=?', (csn,)
    )
    dx = db.query(
        'SELECT * FROM "PAT_ENC_DX" WHERE CAST(PAT_ENC_CSN_ID AS TEXT)=?',
        (csn,),
    )
    reasons = db.query(
        'SELECT * FROM "PAT_ENC_RSN_VISIT" '
        'WHERE CAST(PAT_ENC_CSN_ID AS TEXT)=?',
        (csn,),
    )
    notes = db.query(
        "SELECT note_id, description, note_type, author, created "
        "FROM notes_assembled WHERE pat_enc_csn = ? ORDER BY created",
        (csn,),
    )
    orders = db.query(
        'SELECT ORDER_PROC_ID, PROC_ID_PROC_NAME, ORDERING_DATE, '
        'ORDER_STATUS_C_NAME FROM "ORDER_PROC" '
        'WHERE CAST(PAT_ENC_CSN_ID AS TEXT)=? ORDER BY ORDERING_DATE',
        (csn,),
    )
    meds = db.query(
        'SELECT ORDER_MED_ID, MEDICATION_ID_MEDICATION_NAME, '
        'ORDERING_DATE, DOSAGE '
        'FROM "ORDER_MED" WHERE CAST(PAT_ENC_CSN_ID AS TEXT)=? '
        'ORDER BY ORDERING_DATE',
        (csn,),
    )
    return {
        "encounter": enc, "encounter2": enc2, "diagnoses": dx,
        "reasons": reasons, "notes": notes, "orders": orders, "meds": meds,
    }


# --- Labs -------------------------------------------------------------------

@router.get("/labs/components")
def lab_components() -> list[dict]:
    try:
        rows = db.query(
            'SELECT COMPONENT_ID_NAME AS name, '
            'COUNT(*) AS n, '
            '(SELECT REFERENCE_UNIT FROM "ORDER_RESULTS" r2 '
            ' WHERE r2.COMPONENT_ID_NAME = r.COMPONENT_ID_NAME '
            ' AND r2.REFERENCE_UNIT IS NOT NULL LIMIT 1) AS unit '
            'FROM "ORDER_RESULTS" r '
            'WHERE COMPONENT_ID_NAME IS NOT NULL '
            'GROUP BY COMPONENT_ID_NAME ORDER BY COMPONENT_ID_NAME'
        )
        return rows
    except Exception:
        return [{"name": c["name"], "n": c["count"], "unit": c["unit"],
                 "category": c["category"]}
                for c in fhir.observation_components()]


@router.get("/labs/series")
def lab_series(component: str) -> list[dict]:
    try:
        rows = db.query(
            'SELECT RESULT_DATE AS time, ORD_VALUE AS raw_value, '
            'ORD_NUM_VALUE AS value, REFERENCE_LOW AS ref_low, '
            'REFERENCE_HIGH AS ref_high, REFERENCE_UNIT AS unit, '
            'RESULT_FLAG_C_NAME AS flag, '
            'RESULT_IN_RANGE_YN AS in_range, '
            'ORDER_PROC_ID, LINE '
            'FROM "ORDER_RESULTS" WHERE COMPONENT_ID_NAME=? '
            'ORDER BY RESULT_DATE',
            (component,),
        )
        if rows:
            return rows
    except Exception:
        pass
    return fhir.observation_series(component)


@router.get("/labs/recent")
def lab_recent(limit: int = 12) -> list[dict]:
    """Most recent individual lab results across all components."""
    try:
        rows = db.query(
            'SELECT COMPONENT_ID_NAME AS name, RESULT_DATE AS time, '
            'ORD_VALUE AS value, REFERENCE_UNIT AS unit, '
            'REFERENCE_LOW AS ref_low, REFERENCE_HIGH AS ref_high, '
            'RESULT_FLAG_C_NAME AS flag, RESULT_IN_RANGE_YN AS in_range '
            'FROM "ORDER_RESULTS" '
            'WHERE COMPONENT_ID_NAME IS NOT NULL AND RESULT_DATE IS NOT NULL '
            'AND ORD_VALUE IS NOT NULL AND ORD_VALUE <> "" '
            'ORDER BY RESULT_DATE DESC LIMIT ?',
            (limit,),
        )
        if rows:
            return rows
    except Exception:
        pass
    return []



# --- Vitals (flowsheet) -----------------------------------------------------

@router.get("/vitals/measurements")
def vital_measurements() -> list[dict]:
    """Distinct flowsheet measurements with counts."""
    try:
        return db.query(
            'SELECT FLO_MEAS_ID_FLO_MEAS_NAME AS name, COUNT(*) AS n, '
            '(SELECT UNITS FROM "V_EHI_FLO_MEAS_VALUE" v2 '
            ' WHERE v2.FLO_MEAS_ID_FLO_MEAS_NAME = v.FLO_MEAS_ID_FLO_MEAS_NAME '
            ' AND v2.UNITS <> "" LIMIT 1) AS unit '
            'FROM "V_EHI_FLO_MEAS_VALUE" v '
            'GROUP BY FLO_MEAS_ID_FLO_MEAS_NAME ORDER BY name'
        )
    except Exception:
        return []


@router.get("/vitals/series")
def vital_series(name: str) -> list[dict]:
    try:
        return db.query(
            'SELECT m.RECORDED_TIME AS time, v.MEAS_VALUE_EXTERNAL AS value, '
            'v.UNITS AS unit, v.VALUE_TYPE_C_NAME AS value_type '
            'FROM "V_EHI_FLO_MEAS_VALUE" v '
            'LEFT JOIN "IP_FLWSHT_MEAS" m USING (FSD_ID, LINE) '
            'WHERE v.FLO_MEAS_ID_FLO_MEAS_NAME=? '
            'ORDER BY m.RECORDED_TIME',
            (name,),
        )
    except Exception:
        return []


@router.get("/vitals/recent")
def vital_recent() -> list[dict]:
    """Latest value for each flowsheet measurement that has a value."""
    try:
        return db.query(
            'SELECT v.FLO_MEAS_ID_FLO_MEAS_NAME AS name, '
            'v.MEAS_VALUE_EXTERNAL AS value, v.UNITS AS unit, '
            'm.RECORDED_TIME AS time '
            'FROM "V_EHI_FLO_MEAS_VALUE" v '
            'LEFT JOIN "IP_FLWSHT_MEAS" m USING (FSD_ID, LINE) '
            'WHERE v.MEAS_VALUE_EXTERNAL IS NOT NULL '
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
            'ORDER BY m.RECORDED_TIME DESC'
        )
    except Exception:
        return []



# --- Notes ------------------------------------------------------------------

@router.get("/notes")
def list_notes(
    csn: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict]:
    if q:
        # FTS5 search.
        match = db.fts_query(q)
        if not match:
            return []
        sql = (
            "SELECT n.note_id, n.description, n.note_type, n.author, "
            "n.created, n.pat_enc_csn, "
            "snippet(notes_fts, 2, '<mark>', '</mark>', '…', 20) AS snippet "
            "FROM notes_fts f JOIN notes_assembled n ON n.note_id = f.note_id "
            "WHERE notes_fts MATCH ? "
        )
        params: list = [match]
        if csn:
            sql += "AND n.pat_enc_csn = ? "
            params.append(csn)
        sql += "ORDER BY rank LIMIT ?"
        params.append(limit)
        return db.query(sql, params)
    sql = (
        "SELECT note_id, description, note_type, author, created, pat_enc_csn "
        "FROM notes_assembled "
    )
    params = []
    if csn:
        sql += "WHERE pat_enc_csn = ? "
        params.append(csn)
    sql += "ORDER BY created DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)


@router.get("/notes/{note_id}")
def get_note(note_id: str) -> dict:
    row = db.query_one(
        "SELECT * FROM notes_assembled WHERE note_id = ?", (note_id,)
    )
    if not row:
        raise HTTPException(404, "Note not found")
    return row


# --- Imaging ----------------------------------------------------------------
# Imaging reports are promoted into notes_assembled with note_type='Imaging'
# by the FHIR phase of ingest. This endpoint is just a focused projection so
# the frontend can show a radiology-friendly list without the user scrolling
# past every clinical note.

@router.get("/imaging")
def list_imaging(limit: int = 200) -> list[dict]:
    return db.query(
        "SELECT note_id, description, author, created, pat_enc_csn, "
        "substr(full_text, 1, 280) AS preview "
        "FROM notes_assembled WHERE note_type = 'Imaging' "
        "ORDER BY created DESC LIMIT ?",
        (limit,),
    )


# --- Messages ---------------------------------------------------------------

@router.get("/messages")
def list_messages(q: str | None = None, limit: int = 200) -> list[dict]:
    if q:
        match = db.fts_query(q)
        if not match:
            return []
        sql = (
            "SELECT m.msg_id, m.sent, m.from_user, m.subject, "
            "snippet(messages_fts, 2, '<mark>', '</mark>', '…', 20) AS snippet "
            "FROM messages_fts f "
            "JOIN messages_assembled m ON m.msg_id = f.msg_id "
            "WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?"
        )
        return db.query(sql, (match, limit))
    return db.query(
        "SELECT msg_id, sent, from_user, subject "
        "FROM messages_assembled ORDER BY sent DESC LIMIT ?",
        (limit,),
    )


@router.get("/messages/{msg_id}")
def get_message(msg_id: str) -> dict:
    row = db.query_one(
        "SELECT * FROM messages_assembled WHERE msg_id=?", (msg_id,)
    )
    if not row:
        raise HTTPException(404, "Message not found")
    return row


# --- Full-text search across notes + messages ------------------------------

@router.get("/search")
def global_search(q: str, limit: int = 50) -> dict:
    match = db.fts_query(q)
    if not match:
        return {"notes": [], "messages": [], "q": q}
    notes = db.query(
        "SELECT n.note_id, n.description, n.created, n.note_type, "
        "snippet(notes_fts, 2, '<mark>', '</mark>', '…', 15) AS snippet "
        "FROM notes_fts f JOIN notes_assembled n ON n.note_id = f.note_id "
        "WHERE notes_fts MATCH ? ORDER BY rank LIMIT ?",
        (match, limit),
    )
    msgs = db.query(
        "SELECT m.msg_id, m.subject, m.sent, m.from_user, "
        "snippet(messages_fts, 2, '<mark>', '</mark>', '…', 15) AS snippet "
        "FROM messages_fts f JOIN messages_assembled m ON m.msg_id = f.msg_id "
        "WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?",
        (match, limit),
    )
    return {"notes": notes, "messages": msgs}


# --- FHIR raw ---------------------------------------------------------------

@router.get("/fhir/documents")
def fhir_documents() -> list[dict]:
    return fhir.documents()


@router.get("/fhir/binary/{binary_id}")
def fhir_binary(binary_id: str) -> dict:
    b = fhir.binary_text(binary_id)
    if not b:
        raise HTTPException(404, "Binary not found")
    return b
