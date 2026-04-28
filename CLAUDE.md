# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Backend (Python 3.11+, run from repo root with `.venv` activated):

```sh
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8765   # dev server (no --reload flag by convention)
python -m ingest --source "/path/to/Epic Export" --db data/mychart.db   # CLI ingest
python -m ingest --help
```

Ingest phase flags (each phase is idempotent, so re-run after edits):
`--skip-schema`, `--skip-tsv`, `--skip-fhir`, `--skip-notes`,
`--skip-genome`, `--skip-clinvar`. Pass `--genome-source PATH` to also load
a 23andMe export.

Frontend (from `frontend/`):

```sh
npm install
npm run dev          # Vite on :5173, proxies /api -> 127.0.0.1:8765
npm run build        # tsc -b && vite build
npx tsc --noEmit     # typecheck only (what CI runs)
```

There is no test suite. CI (`.github/workflows/ci.yml`) only runs: `python -c "import backend.main; import ingest.runner"`, `python -m ingest --help`, `npx tsc --noEmit`, and `npm run build`. Validate changes by running those locally.

## Architecture

Three-layer local app. The **only** supported deployment is `127.0.0.1` — do not add LAN-binding or auth; privacy guarantees rely on this.

**`ingest/`** — one-shot pipeline turning an Epic EHI export into a queryable SQLite DB.
- `runner.run_ingest(IngestOptions, progress=...)` is the single entrypoint used by both the CLI (`ingest/__main__.py`) and the backend admin route (which streams `progress` events to the UI via SSE). Progress dicts have shape `{"phase", "status", "message", ...}`.
- Phases: `parse_schema` (HTM data dictionary → `data/schema.json`), `load_tsv` (curated allow-list in `ingest/tables.py` → typed SQLite tables), `load_fhir` (NDJSON bundles → flattened FHIR tables), `assemble_notes` (RTF → text, FTS5 indexes over notes + MyChart messages), `load_genome` (optional: 23andMe `genome_*.txt` → `genome_variants` + `genome_ancestry`, plus a cached NCBI ClinVar download → `clinvar_variants`, GRCh37 only). Genome-only re-ingest is supported when no Epic source is configured.
- ~40 curated clinical tables land in SQLite; the other ~3,600 export tables are streamed from TSV on demand by the backend's browser route.

**`backend/`** — FastAPI, all routes mounted under `/api` from `backend/main.py`.
- `config.py`: env vars (`MYCHART_DB`, `MYCHART_SCHEMA_JSON`, `MYCHART_SOURCE`, `MYCHART_GENOME`) override `data/settings.json`, which is the UI-editable config written from the Setup page. `load_settings()` merges defaults + file.
- `db.py`: every request opens SQLite **read-only** (`mode=ro` URI). `FileNotFoundError` bubbles up and the global handler in `main.py` converts it to HTTP 503 `database_not_ingested` — that's the signal the frontend uses to route users to Setup. Also exposes `fts_query()` for safe FTS5 MATCH construction (raw LLM text would blow up on `-`, `:`, date-like tokens).
- `sql_guard.ensure_safe()`: parses user/LLM SQL with sqlglot, rejects non-SELECT/WITH or multi-statement, injects/clamps a LIMIT. Every SQL path — `/api/sql` and the `run_sql` LLM tool — goes through this.
- `routes/`: `clinical` (curated dashboards: problems, meds, labs, vitals, etc.), `browser` (generic tables list + on-demand TSV streaming for non-ingested tables), `genome` (notable variants, rsid lookup, gene search, ancestry breakdown — backed by the optional 23andMe + ClinVar tables), `conversations` (chat persistence via `chat_store.py` → `data/chats.db`), `admin` (Setup page: validate Epic + 23andMe sources, save settings, start ingest with SSE progress).
- `llm/`: `chat.py` runs the tool-calling loop (capped by `max_tool_turns`) and streams SSE events (`text`/`tool_call`/`tool_result`/`done`/`error`). `providers.py` abstracts Ollama / OpenAI / Anthropic behind one interface. `tools.py` defines the tools the model can invoke (`get_patient_summary`, `list_tables`, `describe_table`, `run_sql`, `search_notes`, `get_note`, `get_message`, `lab_trend`, plus the genome tools `lookup_snp`, `list_notable_variants`, `search_variants_by_gene`, `get_ancestry_summary`) — each is size-capped (`MAX_TEXT_CHARS`, `MAX_ROWS`) to protect context. Cloud provider keys are only read from env (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`), never persisted.

**`frontend/`** — React 18 + Vite + TypeScript + recharts. `src/pages/` has one file per tab. Vite dev proxy forwards `/api` to `127.0.0.1:8765`, so the frontend code always calls relative `/api/...`.

## Conventions & gotchas

- Epic column names are mostly `UPPER_SNAKE_CASE` (e.g. `COMPONENT_ID_NAME`, `ORD_VALUE`, `RESULT_DATE`). When writing SQL or tools against this DB, don't guess columns — read `schema.json` or `PRAGMA table_info`. This is also spelled out in the chat system prompt. The genome-layer tables are the exception: they use lowercase snake_case (`genome_variants(rsid, chromosome, position, genotype)`, `clinvar_variants`, `genome_ancestry`, `genome_meta`).
- `data/` is generated and gitignored (`mychart.db`, `chats.db`, `schema.json`, `settings.json`, `clinvar/`). Don't commit it.
- Re-ingest after editing `ingest/tables.py`: `python -m ingest --source ... --skip-schema --skip-fhir` (or hit "Re-ingest" on the Setup page).
- When adding a new LLM tool, register it in both `tool_specs` (JSON schema) and `dispatch` in `backend/llm/tools.py`, and keep results bounded via `_trunc` / `MAX_ROWS`.
- The `FileNotFoundError` → 503 contract is load-bearing for the first-run UX — don't swallow it in route handlers.
