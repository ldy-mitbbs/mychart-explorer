"""Genome routes: endpoints backing the Genome page in the UI.

Mirrors the patterns in ``clinical.py`` but reads the ``genome_*`` and
``clinvar_variants`` tables produced by ``ingest/load_genome.py``.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .. import db

router = APIRouter(prefix="/genome", tags=["genome"])


def _has_genome() -> bool:
    try:
        tables = set(db.ingested_tables())
    except Exception:
        return False
    return "genome_variants" in tables


def _has_clinvar() -> bool:
    try:
        tables = set(db.ingested_tables())
    except Exception:
        return False
    return "clinvar_variants" in tables


def _ensure_loaded() -> None:
    if not _has_genome():
        raise HTTPException(
            404,
            "Genome data not ingested. Configure a 23andMe export folder "
            "in Setup and run ingest.",
        )


@router.get("/status")
def status() -> dict:
    out: dict[str, Any] = {
        "has_genome": _has_genome(),
        "has_clinvar": _has_clinvar(),
        "meta": {},
        "counts": {},
    }
    if not out["has_genome"]:
        return out
    try:
        meta_rows = db.query("SELECT key, value FROM genome_meta")
        out["meta"] = {r["key"]: r["value"] for r in meta_rows}
    except sqlite3.OperationalError:
        pass
    try:
        c = db.query_one("SELECT COUNT(*) AS n FROM genome_variants")
        out["counts"]["variants"] = c["n"] if c else 0
    except sqlite3.OperationalError:
        pass
    try:
        c = db.query_one("SELECT COUNT(*) AS n FROM genome_ancestry")
        out["counts"]["ancestry_segments"] = c["n"] if c else 0
    except sqlite3.OperationalError:
        pass
    if out["has_clinvar"]:
        try:
            c = db.query_one("SELECT COUNT(*) AS n FROM clinvar_variants")
            out["counts"]["clinvar"] = c["n"] if c else 0
        except sqlite3.OperationalError:
            pass
    return out


@router.get("/ancestry")
def ancestry_summary() -> dict:
    """Compact ancestry summary: per-population %% genome covered."""
    _ensure_loaded()
    try:
        rows = db.query(
            "SELECT ancestry, copy, chromosome, start_pos, end_pos "
            "FROM genome_ancestry"
        )
    except sqlite3.OperationalError:
        return {"populations": [], "segments": []}
    # Each chromosome is diploid (2 copies). Approximate "% of genome" as
    # mean coverage across both copies. We sum segment lengths per ancestry,
    # then divide by 2× the total covered span (rough but informative).
    by_pop_len: dict[str, int] = defaultdict(int)
    total_len = 0
    for r in rows:
        seg = max(0, int(r["end_pos"]) - int(r["start_pos"]))
        by_pop_len[r["ancestry"]] += seg
        total_len += seg
    pops = []
    for name, length in sorted(by_pop_len.items(), key=lambda x: -x[1]):
        pct = (length / total_len * 100) if total_len else 0
        pops.append({
            "ancestry": name,
            "length_bp": length,
            "percent": round(pct, 2),
        })
    return {"populations": pops, "segments": rows}


@router.get("/snp/{rsid}")
def lookup_snp(rsid: str) -> dict:
    _ensure_loaded()
    rsid = rsid.strip()
    if not rsid:
        raise HTTPException(400, "rsid required")
    if not rsid.lower().startswith("rs"):
        rsid = "rs" + rsid.lstrip("Rr").lstrip("Ss")
    row = db.query_one(
        "SELECT rsid, chromosome, position, genotype "
        "FROM genome_variants WHERE rsid=? COLLATE NOCASE",
        (rsid,),
    )
    if not row:
        return {"rsid": rsid, "found": False, "annotations": []}
    annotations: list[dict] = []
    if _has_clinvar():
        annotations = db.query(
            "SELECT gene_symbol, clinical_significance, phenotype, "
            "review_status, variation_id, variant_type "
            "FROM clinvar_variants WHERE rs_id=? COLLATE NOCASE "
            "ORDER BY clinical_significance",
            (rsid,),
        )
    return {
        "rsid": rsid,
        "found": True,
        "genotype": row["genotype"],
        "chromosome": row["chromosome"],
        "position": row["position"],
        "annotations": annotations,
    }


# Categories of clinvar significance the LLM/UI usually want. We surface
# them as a simple inclusion match. Benign variants are intentionally
# excluded by default.
_SIGNIFICANT_KEYWORDS = (
    "Pathogenic",
    "Likely pathogenic",
    "drug response",
    "risk factor",
    "association",
    "protective",
)


@router.get("/notable")
def notable_variants(
    limit: int = Query(200, ge=1, le=1000),
    include_benign: bool = False,
) -> dict:
    """Variants you carry that ClinVar tags as clinically interesting.

    Joins genome_variants × clinvar_variants on rsid, filtering by
    ``clinical_significance`` keywords. Skips no-call genotypes (``--``).
    """
    _ensure_loaded()
    if not _has_clinvar():
        return {
            "variants": [],
            "note": "ClinVar not ingested. Re-run ingest without --skip-clinvar.",
        }
    if include_benign:
        sig_clause = "1=1"
        params: tuple = ()
    else:
        ors = " OR ".join(
            ["c.clinical_significance LIKE ?"] * len(_SIGNIFICANT_KEYWORDS)
        )
        sig_clause = f"({ors})"
        params = tuple(f"%{kw}%" for kw in _SIGNIFICANT_KEYWORDS)
    rows = db.query(
        "SELECT g.rsid, g.chromosome, g.position, g.genotype, "
        "c.gene_symbol, c.clinical_significance, c.phenotype, "
        "c.review_status, c.variation_id, c.variant_type "
        "FROM genome_variants g "
        "JOIN clinvar_variants c ON c.rs_id = g.rsid "
        f"WHERE {sig_clause} "
        "AND g.genotype NOT IN ('--', '') AND g.genotype IS NOT NULL "
        "ORDER BY "
        "  CASE "
        "    WHEN c.clinical_significance LIKE '%Pathogenic%' AND c.clinical_significance NOT LIKE '%Likely%' THEN 0 "
        "    WHEN c.clinical_significance LIKE '%Likely pathogenic%' THEN 1 "
        "    WHEN c.clinical_significance LIKE '%drug response%' THEN 2 "
        "    WHEN c.clinical_significance LIKE '%risk factor%' THEN 3 "
        "    ELSE 4 END, "
        "  c.gene_symbol "
        "LIMIT ?",
        params + (limit,),
    )
    return {"variants": rows, "count": len(rows)}


@router.get("/gene/{symbol}")
def by_gene(symbol: str, limit: int = Query(200, ge=1, le=1000)) -> dict:
    _ensure_loaded()
    sym = symbol.strip().upper()
    if not sym:
        raise HTTPException(400, "gene symbol required")
    if not _has_clinvar():
        return {
            "gene": sym, "variants": [],
            "note": "ClinVar not ingested.",
        }
    rows = db.query(
        "SELECT g.rsid, g.chromosome, g.position, g.genotype, "
        "c.gene_symbol, c.clinical_significance, c.phenotype, "
        "c.review_status, c.variation_id, c.variant_type "
        "FROM clinvar_variants c "
        "JOIN genome_variants g ON g.rsid = c.rs_id "
        "WHERE c.gene_symbol = ? COLLATE NOCASE "
        "AND g.genotype NOT IN ('--', '') AND g.genotype IS NOT NULL "
        "ORDER BY "
        "  CASE "
        "    WHEN c.clinical_significance LIKE '%Pathogenic%' AND c.clinical_significance NOT LIKE '%Likely%' AND c.clinical_significance NOT LIKE '%Conflicting%' THEN 0 "
        "    WHEN c.clinical_significance LIKE '%Likely pathogenic%' THEN 1 "
        "    WHEN c.clinical_significance LIKE '%drug response%' THEN 2 "
        "    WHEN c.clinical_significance LIKE '%risk factor%' THEN 3 "
        "    WHEN c.clinical_significance LIKE '%Conflicting%' THEN 4 "
        "    WHEN c.clinical_significance LIKE '%Benign%' THEN 9 "
        "    ELSE 5 END "
        "LIMIT ?",
        (sym, limit),
    )
    return {"gene": sym, "variants": rows, "count": len(rows)}
