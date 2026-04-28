"""Load 23andMe raw genotype + ancestry data into SQLite.

The 23andMe export bundle is a folder containing:

  * ``genome_<name>_v*_Full_<timestamp>.txt`` — TAB-separated, ``#`` comments,
    columns ``rsid  chromosome  position  genotype``.
  * ``<name>_ancestry_composition*.csv`` — per-region ancestry assignments.

Optionally we enrich genotypes with ClinVar's ``variant_summary.txt.gz`` so
the LLM can answer "do I carry pathogenic variant X for Y" without us
shipping curated rsid lists. The download is cached in
``data/clinvar/variant_summary.txt.gz``; pass ``skip_clinvar=True`` to skip
the network entirely (offline / privacy-conscious users).

All three tables are dropped + recreated on each run, so re-ingesting after
swapping the genome file is safe.
"""

from __future__ import annotations

import csv
import gzip
import io
import re
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterator, Optional

ProgressFn = Optional[Callable[[dict], None]]

# 23andMe v3+v5 raw data uses GRCh37 (build 37 / Annotation Release 104).
DEFAULT_BUILD = "GRCh37"

# NCBI ClinVar — small (~100 MB compressed), updated weekly. We only filter
# down to GRCh37 rows with an rs#, which fits comfortably in SQLite.
CLINVAR_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"
)
CLINVAR_CACHE_NAME = "variant_summary.txt.gz"


def _emit(cb: ProgressFn, **kw) -> None:
    if cb:
        try:
            cb(kw)
        except Exception:
            pass


# --- file discovery ---------------------------------------------------------

def find_genome_files(source: Path) -> dict:
    """Auto-detect the raw genotype file and ancestry CSV.

    ``source`` may be a directory (we search it) or the genome file itself.
    Returns ``{"genome": Path|None, "ancestry": Path|None, "source_dir": Path}``.
    """
    out: dict = {"genome": None, "ancestry": None, "source_dir": None}
    p = source.expanduser()
    if p.is_file():
        out["genome"] = p
        out["source_dir"] = p.parent
        search_dir = p.parent
    elif p.is_dir():
        out["source_dir"] = p
        search_dir = p
        # Prefer the most recent genome_* file if multiple are present.
        genomes = sorted(
            list(p.glob("genome_*.txt")) + list(p.glob("genome_*.tsv")),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if genomes:
            out["genome"] = genomes[0]
    else:
        return out
    ancestry = sorted(search_dir.glob("*ancestry_composition*.csv"))
    if ancestry:
        out["ancestry"] = ancestry[0]
    return out


def describe_genome_source(source: Path) -> dict:
    """UI helper — what's in this genome folder?"""
    info: dict = {"source": str(source), "exists": source.exists()}
    if not source.exists():
        return info
    found = find_genome_files(source)
    info["genome_file"] = str(found["genome"]) if found["genome"] else ""
    info["ancestry_file"] = str(found["ancestry"]) if found["ancestry"] else ""
    info["has_genome"] = bool(found["genome"])
    info["has_ancestry"] = bool(found["ancestry"])
    return info


# --- 23andMe genome TSV -----------------------------------------------------

_RS_PATTERN = re.compile(r"^rs\d+$", re.IGNORECASE)


def _iter_genome_rows(path: Path) -> Iterator[tuple]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            rsid, chrom, pos, geno = parts[0], parts[1], parts[2], parts[3]
            if not rsid or not chrom or not pos:
                continue
            try:
                pos_i = int(pos)
            except ValueError:
                continue
            yield (rsid, chrom, pos_i, geno.strip().upper())


def load_23andme(
    conn: sqlite3.Connection,
    genome_path: Path,
    progress: ProgressFn = None,
) -> int:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS genome_variants")
    cur.execute(
        "CREATE TABLE genome_variants ("
        "  rsid TEXT NOT NULL,"
        "  chromosome TEXT NOT NULL,"
        "  position INTEGER NOT NULL,"
        "  genotype TEXT,"
        "  is_rs INTEGER NOT NULL DEFAULT 0,"
        "  PRIMARY KEY (rsid, chromosome, position)"
        ")"
    )
    rows = 0
    batch: list[tuple] = []
    BATCH = 5000
    t0 = time.time()
    for rsid, chrom, pos, geno in _iter_genome_rows(genome_path):
        batch.append((rsid, chrom, pos, geno, 1 if _RS_PATTERN.match(rsid) else 0))
        if len(batch) >= BATCH:
            cur.executemany(
                "INSERT OR IGNORE INTO genome_variants "
                "(rsid, chromosome, position, genotype, is_rs) VALUES (?,?,?,?,?)",
                batch,
            )
            rows += len(batch)
            batch.clear()
            if rows % 100000 == 0:
                _emit(progress, phase="genome", status="log",
                      message=f"  loaded {rows:,} variants…")
    if batch:
        cur.executemany(
            "INSERT OR IGNORE INTO genome_variants "
            "(rsid, chromosome, position, genotype, is_rs) VALUES (?,?,?,?,?)",
            batch,
        )
        rows += len(batch)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_genome_rsid ON genome_variants(rsid)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_genome_chrom_pos "
        "ON genome_variants(chromosome, position)"
    )
    conn.commit()
    _emit(progress, phase="genome", status="log",
          message=f"genotypes: {rows:,} rows in {time.time()-t0:.1f}s")
    return rows


# --- ancestry CSV -----------------------------------------------------------

def load_ancestry(conn: sqlite3.Connection, ancestry_path: Path) -> int:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS genome_ancestry")
    cur.execute(
        "CREATE TABLE genome_ancestry ("
        "  ancestry TEXT NOT NULL,"
        "  copy INTEGER NOT NULL,"
        "  chromosome TEXT NOT NULL,"
        "  start_pos INTEGER NOT NULL,"
        "  end_pos INTEGER NOT NULL"
        ")"
    )
    rows = 0
    with ancestry_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        batch: list[tuple] = []
        for r in reader:
            try:
                copy = int(r.get("Copy") or 0)
                start_pos = int(r.get("Start Point") or 0)
                end_pos = int(r.get("End Point") or 0)
            except ValueError:
                continue
            anc = (r.get("Ancestry") or "").strip()
            chrom = (r.get("Chromosome") or "").strip()
            if not anc or not chrom:
                continue
            batch.append((anc, copy, chrom, start_pos, end_pos))
        if batch:
            cur.executemany(
                "INSERT INTO genome_ancestry "
                "(ancestry, copy, chromosome, start_pos, end_pos) "
                "VALUES (?,?,?,?,?)",
                batch,
            )
            rows = len(batch)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ancestry_anc ON genome_ancestry(ancestry)"
    )
    conn.commit()
    return rows


# --- ClinVar ----------------------------------------------------------------

def _download_clinvar(dest: Path, progress: ProgressFn = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1_000_000:  # already cached
        _emit(progress, phase="genome", status="log",
              message=f"clinvar: using cached {dest}")
        return dest
    _emit(progress, phase="genome", status="log",
          message=f"clinvar: downloading {CLINVAR_URL} → {dest}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(
        CLINVAR_URL, headers={"User-Agent": "mychart-explorer/0.1"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)
    _emit(progress, phase="genome", status="log",
          message=f"clinvar: downloaded {dest.stat().st_size / 1e6:.1f} MB")
    return dest


# Columns we care about from variant_summary.txt. The file has ~40 columns.
_CV_FIELDS = (
    "RS# (dbSNP)",
    "GeneSymbol",
    "ClinicalSignificance",
    "PhenotypeList",
    "ReviewStatus",
    "VariationID",
    "Assembly",
    "Type",
    "Chromosome",
    "Start",
)


def load_clinvar(
    conn: sqlite3.Connection,
    cache_dir: Path,
    progress: ProgressFn = None,
) -> int:
    """Download (if needed), parse, and load a slim ClinVar table.

    Filters to GRCh37 rows with a real rs#, since that's what 23andMe gives us.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    gz_path = _download_clinvar(cache_dir / CLINVAR_CACHE_NAME, progress)

    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS clinvar_variants")
    cur.execute(
        "CREATE TABLE clinvar_variants ("
        "  rs_id TEXT NOT NULL,"
        "  gene_symbol TEXT,"
        "  clinical_significance TEXT,"
        "  phenotype TEXT,"
        "  review_status TEXT,"
        "  variation_id TEXT,"
        "  variant_type TEXT,"
        "  chromosome TEXT,"
        "  position INTEGER"
        ")"
    )

    t0 = time.time()
    rows = 0
    BATCH = 5000
    batch: list[tuple] = []
    with gzip.open(gz_path, "rb") as gz:
        # variant_summary.txt has a header line starting with '#'.
        text = io.TextIOWrapper(gz, encoding="utf-8", errors="replace", newline="")
        header_line = text.readline().lstrip("#").rstrip("\n")
        header = header_line.split("\t")
        try:
            idx = {f: header.index(f) for f in _CV_FIELDS}
        except ValueError as e:
            raise RuntimeError(
                f"ClinVar header missing expected column: {e}. "
                "The variant_summary.txt format may have changed."
            )
        for line in text:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            assembly = parts[idx["Assembly"]]
            if assembly != "GRCh37":
                continue
            rs_raw = parts[idx["RS# (dbSNP)"]]
            if not rs_raw or rs_raw == "-1":
                continue
            try:
                pos_i = int(parts[idx["Start"]])
            except ValueError:
                pos_i = 0
            batch.append((
                f"rs{rs_raw}",
                parts[idx["GeneSymbol"]] or None,
                parts[idx["ClinicalSignificance"]] or None,
                parts[idx["PhenotypeList"]] or None,
                parts[idx["ReviewStatus"]] or None,
                parts[idx["VariationID"]] or None,
                parts[idx["Type"]] or None,
                parts[idx["Chromosome"]] or None,
                pos_i,
            ))
            if len(batch) >= BATCH:
                cur.executemany(
                    "INSERT INTO clinvar_variants "
                    "(rs_id, gene_symbol, clinical_significance, phenotype, "
                    " review_status, variation_id, variant_type, chromosome, position) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    batch,
                )
                rows += len(batch)
                batch.clear()
        if batch:
            cur.executemany(
                "INSERT INTO clinvar_variants "
                "(rs_id, gene_symbol, clinical_significance, phenotype, "
                " review_status, variation_id, variant_type, chromosome, position) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                batch,
            )
            rows += len(batch)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_clinvar_rs ON clinvar_variants(rs_id)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_clinvar_gene ON clinvar_variants(gene_symbol)"
    )
    conn.commit()
    _emit(progress, phase="genome", status="log",
          message=f"clinvar: {rows:,} rows in {time.time()-t0:.1f}s")
    return rows


# --- meta -------------------------------------------------------------------

def write_meta(
    conn: sqlite3.Connection,
    genome_path: Optional[Path],
    ancestry_path: Optional[Path],
    variant_count: int,
    ancestry_count: int,
    clinvar_count: int,
    build: str = DEFAULT_BUILD,
) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS genome_meta")
    cur.execute(
        "CREATE TABLE genome_meta ("
        "  key TEXT PRIMARY KEY, value TEXT"
        ")"
    )
    from datetime import datetime
    rows = [
        ("source_genome_file", str(genome_path) if genome_path else ""),
        ("source_ancestry_file", str(ancestry_path) if ancestry_path else ""),
        ("genome_build", build),
        ("variant_count", str(variant_count)),
        ("ancestry_segment_count", str(ancestry_count)),
        ("clinvar_row_count", str(clinvar_count)),
        ("ingested_at", datetime.now().isoformat(timespec="seconds")),
    ]
    cur.executemany("INSERT INTO genome_meta (key, value) VALUES (?, ?)", rows)
    conn.commit()


# --- top-level orchestration ------------------------------------------------

def load_all(
    conn: sqlite3.Connection,
    source: Path,
    clinvar_cache_dir: Path,
    skip_clinvar: bool = False,
    progress: ProgressFn = None,
) -> dict:
    """Load every genome-related table. Returns counts."""
    found = find_genome_files(source)
    counts = {"variants": 0, "ancestry": 0, "clinvar": 0}
    if found["genome"]:
        _emit(progress, phase="genome", status="log",
              message=f"genome: parsing {found['genome'].name}")
        counts["variants"] = load_23andme(conn, found["genome"], progress)
    else:
        _emit(progress, phase="genome", status="log",
              message=f"genome: no genome_*.txt found in {source}")

    if found["ancestry"]:
        _emit(progress, phase="genome", status="log",
              message=f"ancestry: parsing {found['ancestry'].name}")
        counts["ancestry"] = load_ancestry(conn, found["ancestry"])
    else:
        _emit(progress, phase="genome", status="log",
              message="ancestry: no *ancestry_composition*.csv found (skipped)")

    if not skip_clinvar and counts["variants"] > 0:
        try:
            counts["clinvar"] = load_clinvar(conn, clinvar_cache_dir, progress)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            _emit(progress, phase="genome", status="log",
                  message=f"clinvar: download failed ({e}); skipping annotation")
        except RuntimeError as e:
            _emit(progress, phase="genome", status="log",
                  message=f"clinvar: parse failed ({e}); skipping annotation")
    elif skip_clinvar:
        _emit(progress, phase="genome", status="log",
              message="clinvar: skipped (--skip-clinvar)")

    write_meta(
        conn,
        found["genome"], found["ancestry"],
        counts["variants"], counts["ancestry"], counts["clinvar"],
    )
    return counts
