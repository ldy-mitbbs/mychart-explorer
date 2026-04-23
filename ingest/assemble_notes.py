"""Reassemble clinical notes and MyChart messages into searchable tables.

Epic stores note text in line-numbered fragment tables:
  HNO_INFO       — one row per note, header (author, type, create time, CSN).
  NOTE_TEXT      — one row per (NOTE_ID, LINE) with a text fragment.
  HNO_PLAIN_TEXT — sibling of NOTE_TEXT for plain-text bodies.

We stitch these into `notes_assembled` and build an FTS5 index.

If the source tables aren't in the allow-list (or the TSVs are empty), the
function simply logs and moves on — this keeps ingest resilient.
"""

from __future__ import annotations

import html
import json
import re
import sqlite3


_RTF_CTRL = re.compile(r"\\[a-zA-Z]+-?\d*\s?|\\[\\{}]|[\{\}]")
_RTF_HEX = re.compile(r"\\'([0-9a-fA-F]{2})")
_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_BLOCK = re.compile(r"</(p|div|br|li|tr|h\d)>", re.I)


def _rtf_to_text(rtf: str) -> str:
    """Lossy RTF -> plain text good enough for search/LLM context.

    Strips RTF control words, groups, and escape sequences. Not a full parser.
    """
    if not rtf:
        return ""
    # Decode hex escapes like \'92 (smart quote) to '?' placeholder.
    s = _RTF_HEX.sub(lambda m: chr(int(m.group(1), 16)) if int(m.group(1), 16) < 128 else "?", rtf)
    s = _RTF_CTRL.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _html_to_text(src: str) -> str:
    """Lossy HTML -> plain text. Keeps block-level line breaks."""
    if not src:
        return ""
    # Drop script/style blocks entirely.
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", src, flags=re.I | re.S)
    # Turn closing block tags into newlines so paragraphs stay separated.
    s = _HTML_BLOCK.sub("\n", s)
    s = _HTML_TAG.sub(" ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s).strip()
    return s


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, name: str) -> set[str]:
    return {r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')}


def assemble(conn: sqlite3.Connection, log=print) -> dict[str, int]:
    cur = conn.cursor()

    # Clean slate.
    cur.executescript(
        """
        DROP TABLE IF EXISTS notes_assembled;
        CREATE TABLE notes_assembled (
            note_id      TEXT PRIMARY KEY,
            pat_enc_csn  TEXT,
            note_type    TEXT,
            author       TEXT,
            created      TEXT,
            description  TEXT,
            full_text    TEXT
        );
        CREATE INDEX idx_notes_csn ON notes_assembled(pat_enc_csn);
        CREATE INDEX idx_notes_created ON notes_assembled(created);
        """
    )

    stats: dict[str, int] = {"notes": 0, "messages": 0}

    # --- Clinical notes (HNO_INFO + NOTE_TEXT / HNO_PLAIN_TEXT) ---
    if _table_exists(conn, "HNO_INFO"):
        hno_cols = _columns(conn, "HNO_INFO")
        id_col = "NOTE_ID" if "NOTE_ID" in hno_cols else None
        if id_col is None:
            # Some Epic exports key on NOTE_ID in a different table; bail.
            log("  HNO_INFO has no NOTE_ID column — skipping notes assembly")
        else:
            # Pick columns defensively.
            def pick(*candidates: str) -> str:
                for c in candidates:
                    if c in hno_cols:
                        return f'h."{c}"'
                return "NULL"

            csn_expr = pick("PAT_ENC_CSN_ID")
            type_expr = pick("NOTE_TYPE_NOADD_C_NAME", "IP_NOTE_TYPE_C_NAME")
            author_expr = pick(
                "CURRENT_AUTHOR_ID_NAME", "CONTACT_SER_NUM_USER_ID_NAME"
            )
            created_expr = pick("CREATE_INSTANT_DTTM", "NOTE_FILE_TIME_DTTM")
            desc_expr = pick("NOTE_DESC", "IP_NOTE_TITLE")

            # Figure out which body tables exist. Epic stores the fragment
            # text in a column called NOTE_TEXT in both NOTE_TEXT and
            # HNO_PLAIN_TEXT tables.
            body_sources = []
            for tbl in ("NOTE_TEXT", "HNO_PLAIN_TEXT"):
                if _table_exists(conn, tbl):
                    cols = _columns(conn, tbl)
                    if "NOTE_ID" in cols and "LINE" in cols and "NOTE_TEXT" in cols:
                        body_sources.append((tbl, "NOTE_TEXT"))

            if not body_sources:
                log("  No NOTE_TEXT / HNO_PLAIN_TEXT present — "
                    "notes will have headers only")

            # Build assembled body per note by concatenating fragments in
            # LINE order. group_concat preserves grouping order by default in
            # SQLite (sufficient for our small per-note line counts after we
            # pre-sort via a subquery).
            # Use UNION ALL across all body source tables.
            if body_sources:
                union_sql = " UNION ALL ".join(
                    f'SELECT "NOTE_ID" AS note_id, CAST("LINE" AS INTEGER) '
                    f'AS line, "{col}" AS txt FROM "{tbl}"'
                    for tbl, col in body_sources
                )
                body_cte = (
                    f"WITH ordered AS ({union_sql}), "
                    "grouped AS ( "
                    "  SELECT note_id, GROUP_CONCAT(txt, '') AS body "
                    "  FROM (SELECT * FROM ordered ORDER BY note_id, line) "
                    "  GROUP BY note_id "
                    ") "
                )
            else:
                body_cte = "WITH grouped AS (SELECT NULL AS note_id, NULL AS body) "

            insert_sql = f"""
                {body_cte}
                INSERT INTO notes_assembled
                    (note_id, pat_enc_csn, note_type, author, created,
                     description, full_text)
                SELECT
                    CAST(h."{id_col}" AS TEXT),
                    CAST({csn_expr} AS TEXT),
                    {type_expr},
                    {author_expr},
                    {created_expr},
                    {desc_expr},
                    COALESCE(g.body, '')
                FROM "HNO_INFO" h
                LEFT JOIN grouped g
                  ON g.note_id = CAST(h."{id_col}" AS TEXT)
            """
            cur.execute(insert_sql)
            conn.commit()
            stats["notes"] = cur.execute(
                "SELECT COUNT(*) FROM notes_assembled"
            ).fetchone()[0]
            log(f"  assembled {stats['notes']} clinical notes")
    else:
        log("  HNO_INFO not present — skipping notes assembly")

    # --- Enrich notes from FHIR DocumentReference + Binary ---
    # Epic exports often omit NOTE_TEXT (rich text) from the TSV bundle, so
    # most notes in HNO_INFO end up with empty bodies. The same narrative is
    # usually attached to a DocumentReference whose identifier value is the
    # NOTE_ID and whose content[].attachment.url points at a Binary.
    enriched = _enrich_notes_from_fhir(conn, log=log)
    if enriched:
        stats["notes_enriched_from_fhir"] = enriched

    # --- MyChart messages ---
    cur.executescript(
        """
        DROP TABLE IF EXISTS messages_assembled;
        CREATE TABLE messages_assembled (
            msg_id    TEXT PRIMARY KEY,
            sent      TEXT,
            from_user TEXT,
            subject   TEXT,
            body      TEXT
        );
        """
    )
    if _table_exists(conn, "MYC_MESG"):
        myc_cols = _columns(conn, "MYC_MESG")

        def pick(*candidates: str) -> str:
            for c in candidates:
                if c in myc_cols:
                    return f'm."{c}"'
            return "NULL"

        id_expr = pick("MESSAGE_ID", "MYC_MESG_ID")
        sent_expr = pick("CREATED_TIME", "SENT_DTTM", "UPDATE_DATE")
        from_expr = pick("FROM_USER_ID_NAME", "SENDER_USER_ID_NAME")
        subj_expr = pick("SUBJECT", "REQUEST_SUBJECT", "MESSAGE_SUBJECT")

        # Stitch RTF body fragments by LINE, then pass through _rtf_to_text.
        if _table_exists(conn, "MYC_MESG_RTF_TEXT"):
            rtf_cols = _columns(conn, "MYC_MESG_RTF_TEXT")
            if {"MESSAGE_ID", "LINE", "RTF_TXT"} <= rtf_cols:
                # Read raw grouped RTF then post-process in Python to strip.
                cur.execute(
                    """
                    INSERT INTO messages_assembled
                        (msg_id, sent, from_user, subject, body)
                    SELECT CAST({id_expr} AS TEXT), {sent_expr},
                           {from_expr}, {subj_expr},
                           (SELECT GROUP_CONCAT(RTF_TXT, '')
                              FROM (SELECT RTF_TXT FROM MYC_MESG_RTF_TEXT r
                                    WHERE r.MESSAGE_ID = m.MESSAGE_ID
                                    ORDER BY CAST(r.LINE AS INTEGER)))
                    FROM MYC_MESG m
                    """.format(
                        id_expr=id_expr, sent_expr=sent_expr,
                        from_expr=from_expr, subj_expr=subj_expr,
                    )
                )
                conn.commit()
                # Now strip RTF in-place.
                rows = cur.execute(
                    "SELECT msg_id, body FROM messages_assembled "
                    "WHERE body IS NOT NULL"
                ).fetchall()
                cur.executemany(
                    "UPDATE messages_assembled SET body=? WHERE msg_id=?",
                    [(_rtf_to_text(b or ""), mid) for mid, b in rows],
                )
            else:
                log("  MYC_MESG_RTF_TEXT missing expected columns; "
                    "messages will be header-only")
                cur.execute(
                    f"""INSERT INTO messages_assembled
                        (msg_id, sent, from_user, subject, body)
                        SELECT CAST({id_expr} AS TEXT), {sent_expr},
                               {from_expr}, {subj_expr}, NULL
                        FROM MYC_MESG m"""
                )
        else:
            cur.execute(
                f"""INSERT INTO messages_assembled
                    (msg_id, sent, from_user, subject, body)
                    SELECT CAST({id_expr} AS TEXT), {sent_expr},
                           {from_expr}, {subj_expr}, NULL
                    FROM MYC_MESG m"""
            )
        stats["messages"] = cur.execute(
            "SELECT COUNT(*) FROM messages_assembled"
        ).fetchone()[0]
        log(f"  assembled {stats['messages']} MyChart messages")

    # --- FTS5 ---
    cur.executescript(
        """
        DROP TABLE IF EXISTS notes_fts;
        CREATE VIRTUAL TABLE notes_fts USING fts5(
            note_id UNINDEXED,
            description,
            full_text,
            tokenize='porter unicode61'
        );
        INSERT INTO notes_fts(note_id, description, full_text)
        SELECT note_id, COALESCE(description,''), COALESCE(full_text,'')
        FROM notes_assembled;

        DROP TABLE IF EXISTS messages_fts;
        CREATE VIRTUAL TABLE messages_fts USING fts5(
            msg_id UNINDEXED,
            subject,
            body,
            tokenize='porter unicode61'
        );
        INSERT INTO messages_fts(msg_id, subject, body)
        SELECT msg_id, COALESCE(subject,''), COALESCE(body,'')
        FROM messages_assembled;
        """
    )
    conn.commit()
    log("  FTS5 indexes built")
    return stats


def _enrich_notes_from_fhir(conn: sqlite3.Connection, log=print) -> int:
    """Fill in empty notes_assembled rows from FHIR DocumentReference/Binary.

    For each DocumentReference, the first identifier.value is the Epic
    NOTE_ID. content[].attachment.url looks like 'Binary/<id>' and points at
    a base64-decoded row in fhir_binaries. We prefer the text/html attachment
    (simpler to strip) and fall back to text/rtf.

    Returns the number of notes_assembled rows updated.
    """
    if not (_table_exists(conn, "fhir_resources") and _table_exists(conn, "fhir_binaries")):
        return 0
    if not _table_exists(conn, "notes_assembled"):
        return 0

    cur = conn.cursor()
    binaries: dict[str, tuple[str, str]] = {
        r[0]: (r[1] or "", r[2] or "")
        for r in cur.execute("SELECT id, content_type, text FROM fhir_binaries")
    }
    if not binaries:
        return 0

    existing_ids: set[str] = {
        r[0]
        for r in cur.execute(
            "SELECT note_id FROM notes_assembled "
            "WHERE full_text IS NULL OR full_text = ''"
        )
    }

    updates: list[tuple[str, str, str, str, str]] = []
    inserts: list[tuple[str, str, str, str, str, str, str]] = []

    rows = cur.execute(
        "SELECT json FROM fhir_resources WHERE resource_type='DocumentReference'"
    ).fetchall()
    for (raw,) in rows:
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            continue
        note_id = ""
        for ident in doc.get("identifier") or []:
            val = ident.get("value") or ""
            # Epic NOTE_IDs are numeric strings; the other identifier is a
            # long dotted OID — skip that one.
            if val and val.isdigit():
                note_id = val
                break
        if not note_id:
            continue

        # Pick the best attachment: prefer HTML, fall back to RTF, else anything.
        best_text = ""
        best_ct = ""
        for c in doc.get("content") or []:
            att = c.get("attachment") or {}
            url = att.get("url") or ""
            ct = (att.get("contentType") or "").lower()
            if not url.startswith("Binary/"):
                continue
            bin_id = url.split("/", 1)[1]
            ct_bin, txt = binaries.get(bin_id, ("", ""))
            if not txt:
                continue
            ct = ct or ct_bin
            if "html" in ct:
                plain = _html_to_text(txt)
            elif "rtf" in ct:
                plain = _rtf_to_text(txt)
            else:
                plain = txt
            if not plain:
                continue
            # Prefer html > rtf > other; longer also wins within same tier.
            tier = 2 if "html" in ct else 1 if "rtf" in ct else 0
            cur_tier = 2 if "html" in best_ct else 1 if "rtf" in best_ct else 0
            if tier > cur_tier or (tier == cur_tier and len(plain) > len(best_text)):
                best_text = plain
                best_ct = ct

        if not best_text:
            continue

        desc = (doc.get("type") or {}).get("text") or ""
        created = (
            doc.get("date")
            or (doc.get("context") or {}).get("period", {}).get("start")
            or ""
        )
        author = ""
        for a in doc.get("author") or []:
            disp = a.get("display")
            if disp:
                author = disp
                break
        note_type = desc

        if note_id in existing_ids:
            updates.append((best_text, desc, created, author, note_id))
        else:
            inserts.append(
                (note_id, "", note_type, author, created, desc, best_text)
            )

    if updates:
        cur.executemany(
            "UPDATE notes_assembled SET "
            "full_text = ?, "
            "description = COALESCE(NULLIF(description,''), ?), "
            "created     = COALESCE(NULLIF(created,''),     ?), "
            "author      = COALESCE(NULLIF(author,''),      ?) "
            "WHERE note_id = ?",
            updates,
        )
    if inserts:
        cur.executemany(
            "INSERT OR IGNORE INTO notes_assembled "
            "(note_id, pat_enc_csn, note_type, author, created, description, full_text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            inserts,
        )
    conn.commit()
    total = len(updates) + len(inserts)
    log(f"  enriched {len(updates)} notes + inserted {len(inserts)} from FHIR")
    return total
