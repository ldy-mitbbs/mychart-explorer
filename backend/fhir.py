"""Helpers for pulling flattened data out of the fhir_resources JSON blobs."""

from __future__ import annotations

import json
from typing import Any, Iterable

from . import db


def _cc_text(cc: dict | None) -> str | None:
    if not cc:
        return None
    if cc.get("text"):
        return cc["text"]
    for c in cc.get("coding", []) or []:
        if c.get("display"):
            return c["display"]
    return None


def _ref_display(ref: dict | None) -> str | None:
    if not ref:
        return None
    return ref.get("display") or ref.get("reference")


def all_of(resource_type: str) -> Iterable[dict]:
    rows = db.query(
        "SELECT json FROM fhir_resources WHERE resource_type = ? ORDER BY id",
        (resource_type,),
    )
    for row in rows:
        try:
            yield json.loads(row["json"])
        except json.JSONDecodeError:
            continue


def one(resource_type: str, rid: str) -> dict | None:
    row = db.query_one(
        "SELECT json FROM fhir_resources WHERE resource_type=? AND id=?",
        (resource_type, rid),
    )
    if not row:
        return None
    try:
        return json.loads(row["json"])
    except json.JSONDecodeError:
        return None


# --- Flatteners returning plain dicts for the UI -----------------------------

def patient_summary() -> dict[str, Any]:
    p = next(all_of("Patient"), None)
    if not p:
        return {}
    name = ""
    if p.get("name"):
        n = p["name"][0]
        name = (n.get("text")
                or " ".join(n.get("given", []) + [n.get("family", "")]).strip())
    mrn = None
    for ident in p.get("identifier", []) or []:
        t = (ident.get("type") or {}).get("text", "")
        if t in {"MRN", "MR"} or "MRN" in t.upper():
            mrn = ident.get("value")
            break
    addr = ""
    if p.get("address"):
        a = p["address"][0]
        addr = ", ".join(
            filter(None, [
                " ".join(a.get("line", []) or []),
                a.get("city"), a.get("state"), a.get("postalCode"),
            ])
        )
    phones = [t.get("value") for t in p.get("telecom", []) or []
              if t.get("system") == "phone"]
    emails = [t.get("value") for t in p.get("telecom", []) or []
              if t.get("system") == "email"]
    return {
        "id": p.get("id"),
        "name": name,
        "birthDate": p.get("birthDate"),
        "gender": p.get("gender"),
        "mrn": mrn,
        "address": addr,
        "phones": phones,
        "emails": emails,
        "deceasedDateTime": p.get("deceasedDateTime"),
    }


def conditions() -> list[dict]:
    out = []
    for r in all_of("Condition"):
        out.append({
            "id": r.get("id"),
            "code": _cc_text(r.get("code")),
            "clinicalStatus": _cc_text(r.get("clinicalStatus")),
            "verificationStatus": _cc_text(r.get("verificationStatus")),
            "category": ", ".join(
                filter(None, (_cc_text(c) for c in r.get("category", []) or []))
            ),
            "onsetDateTime": r.get("onsetDateTime"),
            "recordedDate": r.get("recordedDate"),
            "abatementDateTime": r.get("abatementDateTime"),
            "note": "\n".join(
                n.get("text", "") for n in r.get("note", []) or []
            ).strip(),
        })
    out.sort(
        key=lambda x: x.get("onsetDateTime") or x.get("recordedDate") or "",
        reverse=True,
    )
    return out


def allergies() -> list[dict]:
    out = []
    for r in all_of("AllergyIntolerance"):
        reactions = []
        for rx in r.get("reaction", []) or []:
            for m in rx.get("manifestation", []) or []:
                txt = _cc_text(m)
                if txt:
                    reactions.append(txt)
        out.append({
            "id": r.get("id"),
            "substance": _cc_text(r.get("code")),
            "clinicalStatus": _cc_text(r.get("clinicalStatus")),
            "verificationStatus": _cc_text(r.get("verificationStatus")),
            "criticality": r.get("criticality"),
            "recordedDate": r.get("recordedDate"),
            "reactions": reactions,
        })
    return out


def medications() -> list[dict]:
    out = []
    for r in all_of("MedicationRequest"):
        med = _cc_text(r.get("medicationCodeableConcept"))
        if not med and r.get("medicationReference"):
            med = _ref_display(r["medicationReference"])
        dosage_text = None
        if r.get("dosageInstruction"):
            dosage_text = r["dosageInstruction"][0].get("text")
        out.append({
            "id": r.get("id"),
            "status": r.get("status"),
            "intent": r.get("intent"),
            "medication": med,
            "authoredOn": r.get("authoredOn"),
            "requester": _ref_display(r.get("requester")),
            "reason": ", ".join(
                filter(None, (_cc_text(c)
                              for c in r.get("reasonCode", []) or []))
            ),
            "dosage": dosage_text,
        })
    out.sort(key=lambda x: x.get("authoredOn") or "", reverse=True)
    return out


def encounters() -> list[dict]:
    out = []
    for r in all_of("Encounter"):
        period = r.get("period") or {}
        types = ", ".join(
            filter(None, (_cc_text(t) for t in r.get("type", []) or []))
        )
        reasons = ", ".join(
            filter(None, (_cc_text(t) for t in r.get("reasonCode", []) or []))
        )
        location = None
        for loc in r.get("location", []) or []:
            location = _ref_display(loc.get("location")) or location
        out.append({
            "id": r.get("id"),
            "status": r.get("status"),
            "class": (r.get("class") or {}).get("display")
                     or (r.get("class") or {}).get("code"),
            "type": types,
            "reason": reasons,
            "start": period.get("start"),
            "end": period.get("end"),
            "location": location,
            "serviceProvider": _ref_display(r.get("serviceProvider")),
        })
    out.sort(key=lambda x: x.get("start") or "", reverse=True)
    return out


def immunizations() -> list[dict]:
    out = []
    for r in all_of("Immunization"):
        out.append({
            "id": r.get("id"),
            "vaccine": _cc_text(r.get("vaccineCode")),
            "status": r.get("status"),
            "date": r.get("occurrenceDateTime"),
            "lotNumber": r.get("lotNumber"),
            "site": _cc_text(r.get("site")),
            "route": _cc_text(r.get("route")),
        })
    out.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out


def procedures() -> list[dict]:
    out = []
    for r in all_of("Procedure"):
        out.append({
            "id": r.get("id"),
            "code": _cc_text(r.get("code")),
            "status": r.get("status"),
            "performed": r.get("performedDateTime")
                         or (r.get("performedPeriod") or {}).get("start"),
        })
    out.sort(key=lambda x: x.get("performed") or "", reverse=True)
    return out


# --- Observations (labs + vitals) -------------------------------------------

def _obs_value(r: dict) -> tuple[Any, str | None]:
    if "valueQuantity" in r:
        vq = r["valueQuantity"]
        return vq.get("value"), vq.get("unit")
    if "valueCodeableConcept" in r:
        return _cc_text(r["valueCodeableConcept"]), None
    if "valueString" in r:
        return r["valueString"], None
    if "valueBoolean" in r:
        return r["valueBoolean"], None
    return None, None


def _obs_time(r: dict) -> str | None:
    return (r.get("effectiveDateTime")
            or (r.get("effectivePeriod") or {}).get("start")
            or r.get("issued"))


def observation_components() -> list[dict]:
    """List distinct labs/vitals by display name + category + unit."""
    seen: dict[tuple[str, str], dict] = {}
    for r in all_of("Observation"):
        name = _cc_text(r.get("code")) or "(unknown)"
        cat = ", ".join(
            filter(None, (_cc_text(c) for c in r.get("category", []) or []))
        ) or "other"
        _val, unit = _obs_value(r)
        key = (cat, name)
        entry = seen.setdefault(key, {
            "name": name, "category": cat, "unit": unit, "count": 0,
        })
        entry["count"] += 1
        if not entry.get("unit") and unit:
            entry["unit"] = unit
    return sorted(seen.values(), key=lambda x: (x["category"], x["name"]))


def observation_series(name: str) -> list[dict]:
    """Time series for a given observation display name."""
    out = []
    for r in all_of("Observation"):
        if _cc_text(r.get("code")) != name:
            continue
        val, unit = _obs_value(r)
        ref_low = None
        ref_high = None
        refs = r.get("referenceRange") or []
        if refs:
            ref_low = (refs[0].get("low") or {}).get("value")
            ref_high = (refs[0].get("high") or {}).get("value")
        interp = ", ".join(
            filter(None, (_cc_text(c)
                          for c in r.get("interpretation", []) or []))
        )
        out.append({
            "id": r.get("id"),
            "time": _obs_time(r),
            "value": val,
            "unit": unit,
            "refLow": ref_low,
            "refHigh": ref_high,
            "interpretation": interp,
        })
    out.sort(key=lambda x: x.get("time") or "")
    return out


def documents() -> list[dict]:
    out = []
    for r in all_of("DocumentReference"):
        content = r.get("content") or []
        attachment = content[0].get("attachment") if content else {}
        binary_id = None
        if attachment and attachment.get("url", "").startswith("Binary/"):
            binary_id = attachment["url"].split("/", 1)[1]
        out.append({
            "id": r.get("id"),
            "type": _cc_text(r.get("type")),
            "category": ", ".join(
                filter(None, (_cc_text(c) for c in r.get("category", []) or []))
            ),
            "date": r.get("date"),
            "status": r.get("status"),
            "docStatus": r.get("docStatus"),
            "binaryId": binary_id,
            "contentType": (attachment or {}).get("contentType"),
            "description": r.get("description"),
        })
    out.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out


def binary_text(binary_id: str) -> dict | None:
    row = db.query_one(
        "SELECT id, content_type, text FROM fhir_binaries WHERE id=?",
        (binary_id,),
    )
    return dict(row) if row else None
