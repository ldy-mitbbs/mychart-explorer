"""Parse Epic Clarity HTML data-dictionary files into a JSON schema.

Each `EHITables Schema/<TABLE>.htm` file is Epic's standard data dictionary:
- a header with the table name
- a description paragraph
- a "Primary Key" section listing one or more PK columns
- a "Column Information" table with numbered rows of
  Name / Type / Discontinued? and a following description row.

We parse all of them (best-effort; malformed files are skipped) into
`data/schema.json`:

    {
      "ALLERGY": {
        "description": "...",
        "primary_key": ["ALLERGY_ID"],
        "columns": [
          {"name": "ALLERGY_ID", "type": "NUMERIC",
           "discontinued": false, "description": "..."},
          ...
        ]
      },
      ...
    }
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_one(path: Path) -> dict | None:
    try:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"),
                             "lxml")
    except Exception:
        return None

    header = soup.select_one("table.Header2 td")
    if not header:
        return None
    table_name = _clean(header.get_text())

    # Description (first T1Value under KeyValue).
    desc_cell = soup.select_one("table.KeyValue td.T1Value td.T1Value") \
        or soup.select_one("table.KeyValue td.T1Value")
    description = _clean(desc_cell.get_text()) if desc_cell else ""

    # Find SubHeader3 sections (Primary Key, Column Information).
    primary_key: list[str] = []
    columns: list[dict] = []

    for subhdr in soup.select("table.SubHeader3"):
        label = _clean(subhdr.get_text()).lower()
        sibling = subhdr.find_next_sibling("table")
        if sibling is None:
            continue

        if "primary key" in label:
            for tr in sibling.select("tr"):
                tds = tr.find_all("td")
                # PK rows have: name | ordinal | spacer
                if len(tds) >= 2 and tds[0].get_text(strip=True) \
                        and tds[1].get_text(strip=True).isdigit():
                    primary_key.append(_clean(tds[0].get_text()))

        elif "column information" in label:
            rows = sibling.select("tr")
            i = 0
            while i < len(rows):
                tds = rows[i].find_all("td", recursive=False)
                # Header row for a column: [ordinal, name, type, discontinued, spacer]
                if len(tds) >= 4 and tds[0].get_text(strip=True).isdigit():
                    name = _clean(tds[1].get_text())
                    col_type = _clean(tds[2].get_text())
                    discontinued = _clean(tds[3].get_text()).lower().startswith("y")
                    col_desc = ""
                    # Description typically in the *next* row, inside a nested
                    # table. Scan the next few rows for a description cell.
                    for j in range(i + 1, min(i + 3, len(rows))):
                        inner = rows[j].select_one("td table.SubList")
                        if inner:
                            # Last <td> inside the inner SubList is the description.
                            desc_tds = inner.select("td")
                            if desc_tds:
                                col_desc = _clean(desc_tds[-1].get_text())
                            break
                    columns.append({
                        "name": name,
                        "type": col_type,
                        "discontinued": discontinued,
                        "description": col_desc,
                    })
                i += 1

    if not columns:
        return None

    return {
        "name": table_name,
        "description": description,
        "primary_key": primary_key,
        "columns": columns,
    }


def parse_schema_dir(schema_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for htm in sorted(schema_dir.glob("*.htm")):
        parsed = parse_one(htm)
        if parsed:
            out[parsed["name"]] = parsed
    return out


def write_schema_json(schema_dir: Path, out_path: Path) -> int:
    data = parse_schema_dir(schema_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return len(data)
