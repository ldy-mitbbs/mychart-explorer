"""Ingest CLI wrapper around ``ingest.runner``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .runner import IngestOptions, run_ingest


def _print(evt: dict) -> None:
    phase = evt.get("phase", "")
    status = evt.get("status", "")
    msg = evt.get("message", "")
    prefix = {"start": "->", "end": "OK", "error": "!!"}.get(status, "  ")
    print(f"{prefix} [{phase}] {msg}", flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m ingest")
    p.add_argument(
        "--source", required=True,
        help="Path to the MyChart export root "
             "(contains 'EHITables', 'EHITables Schema', 'FHIR').",
    )
    p.add_argument("--db", default="data/mychart.db",
                   help="SQLite output path (default: data/mychart.db).")
    p.add_argument("--schema-json", default="data/schema.json",
                   help="Parsed schema output path (default: data/schema.json).")
    p.add_argument("--skip-tsv", action="store_true")
    p.add_argument("--skip-fhir", action="store_true")
    p.add_argument("--skip-notes", action="store_true")
    p.add_argument("--skip-schema", action="store_true")
    args = p.parse_args(argv)

    opts = IngestOptions(
        source=Path(args.source).expanduser(),
        db=Path(args.db),
        schema_json=Path(args.schema_json),
        skip_schema=args.skip_schema,
        skip_tsv=args.skip_tsv,
        skip_fhir=args.skip_fhir,
        skip_notes=args.skip_notes,
    )
    result = run_ingest(opts, progress=_print)
    if not result.ok:
        print(f"ERROR: {result.message}", file=sys.stderr)
        return 2
    print(f"\nDone. DB -> {result.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
