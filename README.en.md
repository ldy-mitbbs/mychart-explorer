# MyChart Explorer

> 中文版: [README.md](README.md)

A **local, private** web app to browse your Epic MyChart (EHI) export and ask
an LLM questions about your health data. Default LLM backend is a local
[Ollama](https://ollama.com) model, so your records never leave your machine
unless you explicitly opt in to a cloud provider.

> ⚠️ **This is not a medical device.** It is a personal data-exploration tool.
> Do not rely on it for clinical decisions.

## Features

- **No-CLI setup**: point at your export folder from the in-app **Setup**
  page and click *Start ingest*. Progress streams live.
- **Curated dashboard**: summary, problems, medications, allergies, labs
  (with trend charts + reference ranges), vitals, immunizations, history,
  encounters with full detail, clinical notes with FTS5 search, MyChart
  messages (RTF → text), all flattened FHIR resources.
- **Generic table browser**: every table in your Epic export (~3,700 tables)
  — ingested ones via SQLite, the rest streamed from TSV on demand — with
  column descriptions from the Epic data dictionary as hover tooltips.
- **Read-only SQL console**: SELECT-only, auto-LIMITed, parse-validated with
  `sqlglot`.
- **AI chat** with tool-calling: the model can call
  `get_patient_summary`, `list_tables`, `describe_table`, `run_sql`,
  `search_notes`, `get_note`, `get_message`, and `lab_trend`. Responses cite
  sources like `[note:123]`, `[msg:456]`, `[table:PROBLEMS code=...]`.
- **Pluggable LLM**: Ollama (default, local), OpenAI, or Anthropic. Cloud
  providers show a red *"PHI sent to …"* banner while active.
- **Bilingual UI (English / 简体中文)**: toggle the language from the header.
  The choice persists in localStorage and auto-detects `zh-*` browsers on
  first visit — handy for sharing the app with family members who read
  Chinese more comfortably than English. Ask questions in Chinese and the
  local LLM will reply in Chinese.

## Screenshots

![Ask AI answering a question with note and lab-trend citations](docs/screenshots/chat1.png)

![Same question answered in Chinese — the local model handles multilingual queries](docs/screenshots/chat2.png)

![Summary dashboard with active problems, latest vitals, and recent labs](docs/screenshots/summary.png)

![Lab trend chart for HEMOGLOBIN A1C](docs/screenshots/labs.png)

![Setup page showing ingestion state](docs/screenshots/setup.png)

## Architecture

```
mychart-explorer/
  ingest/       Parse schema HTM + load TSV + load FHIR NDJSON -> SQLite
                Reassemble notes + MyChart messages + FTS5 indexes
  backend/      FastAPI (localhost-only) + SQL guard + LLM router + tools
                Admin routes for UI-driven ingestion
  frontend/     React + Vite + TypeScript + recharts
  data/         mychart.db, schema.json, settings.json (generated, gitignored)
```

## Prerequisites

- **Python** 3.11+ (the backend uses PEP 604 `X | None` union syntax, which requires 3.10+; 3.11+ is recommended). macOS still ships Python 3.9 as `python3`, so check with `python3 --version` first. If you need a newer one:
  - **macOS** (Homebrew): `brew install python@3.12`, then use `python3.12` below.
  - **Ubuntu/Debian**: `sudo apt install python3.12 python3.12-venv`.
  - **Windows**: install from [python.org](https://www.python.org/downloads/) and use `py -3.12`.
- **Node.js** 18+
- **Your Epic MyChart export** — request it from your patient portal. Unzip
  it somewhere convenient; the folder should contain `EHITables/` (TSVs),
  `EHITables Schema/` (HTML data dictionary), and `FHIR/` (NDJSON bundles).
- **Optional: [Ollama](https://ollama.com)** for local LLM chat.

## Quick start

```sh
git clone https://github.com/ldy-mitbbs/mychart-explorer.git
cd mychart-explorer

# 1. Python env + deps — make sure the interpreter is 3.11+.
#    Replace `python3.12` with whichever 3.11+ binary you installed.
python3.12 -m venv .venv
source .venv/bin/activate
python -V   # should print 3.11 or newer
pip install -r requirements.txt

# 2. Start the backend (in one terminal)
uvicorn backend.main:app --host 127.0.0.1 --port 8765

# 3. Start the frontend (in another terminal)
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

On first launch the app will route you to the **Setup** page. Paste the
absolute path to your Epic export, click *Validate*, then *Save*, then
*Start ingest*. Progress streams to the UI.

### CLI alternative

Prefer scripting? The same pipeline is exposed as a CLI:

```sh
python -m ingest --source "/path/to/your/Epic Export" --db data/mychart.db
```

## LLM setup

### Local (recommended)

```sh
brew install ollama           # or see ollama.com for your platform
ollama serve &
ollama pull qwen3.5            # default; see the size guide below for alternatives
```

In the app's **Ask AI** tab → *Settings*, pick a model from the dropdown
(populated from `ollama list`). The chat uses tool calls to query your
SQLite DB, so **stick to models tagged `tools`** on
[ollama.com/library](https://ollama.com/library).

#### Picking a model for your RAM

Rough VRAM/unified-memory budget at the default Q4 quantization
(≈ `params × 0.6 GB`, plus a few GB for context). If you're CPU-only,
the same numbers apply to system RAM, but expect slower tokens/sec.

| Your RAM    | Recommended tool-capable models (Ollama tag)                          |
| ----------- | --------------------------------------------------------------------- |
| 4–6 GB      | `qwen3:1.7b`, `qwen2.5:1.5b`, `granite4:1b`, `granite4:3b`            |
| 8 GB        | `qwen3:4b`, `qwen2.5:3b`, `phi4-mini:3.8b`, `granite3.3:2b`           |
| 12–16 GB    | `qwen3:8b` *(sweet spot)*, `qwen2.5:7b`, `qwen3.5:9b`, `granite3.3:8b`|
| 24–32 GB    | `qwen3:14b`, `phi4:14b`, `qwen3.5:27b` (tight), `mistral-small:24b`, `qwen3.6:27b` † |
| 48–64 GB    | `qwen3:30b` (MoE, fast), `gpt-oss:20b`, `qwen3:32b`, `qwen3.5:35b`, `qwen3.6:35b` †  |
| 96 GB+      | `qwen3:235b` (MoE), `gpt-oss:120b`, `qwen3.5:122b`                    |

Notes:

- **Qwen 3 / 3.5** (Alibaba) is the current go-to open family — strong tool
  calling and ships in many sizes from 0.6B up to 235B MoE.
- **Qwen3 30B MoE** only activates ~3B params per token, so it runs close to
  7B speed while reasoning like a much larger model — great if you have the
  RAM to hold the weights.
- **Phi-4-mini / Phi-4** (Microsoft) are excellent at reasoning for their size.
- **Granite 4** / **Granite 3.3** (IBM) are small, fast, and tool-tuned —
  handy on 8 GB laptops.
- **gpt-oss** (OpenAI open-weight) and **Mistral Small 3** are solid
  mid-to-large options. Skip base **Gemma 3** for this app — it doesn't
  expose tool calling; use **Gemma 4** if you want a Google model.
- If a model behaves oddly with tools, drop one size tier or switch to a
  `qwen3` tag.

† **qwen3.6** is brand new (released April 2026) and only ships in 27B/35B.
It's a `thinking` model with strong agentic coding scores, but tool-call
templates for fresh releases can be rough for the first week or two — if you
see malformed tool calls, fall back to `qwen3:32b` or `qwen3.5:27b`.

### Cloud (opt-in)

Set the key **before** starting the backend:

```sh
export OPENAI_API_KEY=sk-...      # or
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

Then pick the provider in the chat settings drawer. A banner will flag that
cloud calls are active. **Your PHI will be transmitted to that provider** for
each turn, so only enable this if you're comfortable with their data policy.

## Privacy & security

- Backend binds to `127.0.0.1` only. Nothing listens on your LAN.
- SQLite is opened read-only at runtime.
- The `/api/sql` endpoint parses every query with `sqlglot`, rejects anything
  that isn't a `SELECT`/`WITH`, and auto-injects a row limit.
- `data/` (containing your ingested DB and settings) is gitignored.
- The app ships no telemetry.

## Env vars

All env vars are optional — you can configure the app from the Setup page instead.

| Name | Default | Purpose |
|---|---|---|
| `MYCHART_SOURCE` | — | Override source folder (else use Setup page) |
| `MYCHART_DB` | `data/mychart.db` | Output SQLite path |
| `MYCHART_SCHEMA_JSON` | `data/schema.json` | Parsed data-dictionary path |
| `OPENAI_API_KEY` | — | Enables OpenAI provider |
| `ANTHROPIC_API_KEY` | — | Enables Anthropic provider |

## Ingest flags

```sh
python -m ingest --source ... --db ... [--skip-schema] [--skip-tsv] [--skip-fhir] [--skip-notes]
```

Each phase is idempotent and independent, so it's safe to re-run after
editing the curated-tables list in `ingest/tables.py`.

## Adding more tables

By default ~40 clinical tables are loaded into SQLite for fast access. Any
other table from your export is still reachable on demand via the **Tables
browser** (streamed from TSV). To promote a table to SQLite:

1. Add its name (and optional index columns) to `ingest/tables.py`.
2. Re-run the ingest (Setup page → *Re-ingest*, or the CLI with
   `--skip-schema --skip-fhir`).

## Disclaimer

This project is not affiliated with Epic Systems, any health system, or any
electronic-health-record vendor. Use at your own risk. The authors are not
clinicians and this is not medical advice.

## License

[MIT](LICENSE)
