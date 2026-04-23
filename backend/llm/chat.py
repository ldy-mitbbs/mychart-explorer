"""Chat route: runs a tool-calling loop with the selected LLM provider,
streams events to the client over SSE.

Wire format (one SSE `data:` line per event, then `\\n\\n`):
  {"type": "text",      "text": "..."}         incremental assistant text
  {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
  {"type": "tool_result","id": "...", "name": "...", "result": "..." }
  {"type": "done"}
  {"type": "error", "message": "..."}
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import chat_store
from ..config import load_settings, save_settings
from .providers import make_provider
from .tools import dispatch, tool_specs


router = APIRouter()

DEFAULT_MAX_TURNS = 20
MIN_MAX_TURNS = 1
MAX_MAX_TURNS = 100


SYSTEM_PROMPT = """\
You are a careful health-data analyst helping the user explore their own Epic MyChart export.
The data is a single patient's record. Assume "the patient" and "me" mean the same person.

You have these tools:
- get_patient_summary — best default for broad questions.
- list_tables / describe_table — inspect the SQL schema before writing SQL.
- run_sql — SQLite SELECT against the patient's database. ALWAYS cap rows.
- search_notes — FTS5 over clinical notes + MyChart messages. Returns IDs + snippets.
- get_note / get_message — retrieve full text by id.
- lab_trend — time series for a named lab component.
- vitals_trend — time series for a flowsheet vital (BP, pulse, temp, weight, etc.).

Rules:
1. Prefer precise answers grounded in the data. If you don't have evidence, say so.
2. Cite sources inline like [note:<NOTE_ID>], [msg:<MSG_ID>], or [table:<TABLE> <col>=<value>].
3. Never invent medications, diagnoses, dates, or values.
4. You are not a clinician. Don't give medical advice; summarise and explain what's in the record.
5. Keep answers concise. Use short sections or bullets when helpful.
6. Before writing SQL against a table, call describe_table (or list_tables) to learn the REAL column names. Column names are mostly UPPER_SNAKE_CASE (e.g. COMPONENT_ID_NAME, ORD_VALUE, RESULT_DATE in ORDER_RESULTS). Do not guess columns like `component` or `value`.
7. For lab values over time prefer the lab_trend tool — it accepts substrings (e.g. "ALT", "A1C") and will suggest candidates if nothing matches.
8. For vitals / flowsheet questions (blood pressure, pulse, temperature, weight, BMI, SpO2, respirations) use vitals_trend. Do NOT try to read values from IP_FLWSHT_MEAS — that table only stores reading metadata. Values live in V_EHI_FLO_MEAS_VALUE.MEAS_VALUE_EXTERNAL joined to IP_FLWSHT_MEAS via (FSD_ID, LINE). Blood pressure is stored as a single string like "118/72".
9. If a tool returns an `error` with a `hint`, use the hint's column list to fix your query instead of re-guessing.
10. If a broad search returns no results, try 1–2 alternative queries (synonyms, broader terms) before giving up.
"""


class ChatRequest(BaseModel):
    messages: list[dict]
    settings_override: dict | None = None
    conversation_id: str | None = None
    persist: bool = True


class SettingsPatch(BaseModel):
    llm_provider: str | None = None
    ollama_model: str | None = None
    ollama_url: str | None = None
    openai_model: str | None = None
    anthropic_model: str | None = None
    max_tool_turns: int | None = None


@router.get("/settings")
def get_settings() -> dict:
    s = load_settings()
    # Never leak API keys — they aren't stored here anyway; just echo state.
    s["has_openai_key"] = bool(__import__("os").environ.get("OPENAI_API_KEY"))
    s["has_anthropic_key"] = bool(
        __import__("os").environ.get("ANTHROPIC_API_KEY")
    )
    return s


@router.post("/settings")
def update_settings(patch: SettingsPatch) -> dict:
    s = load_settings()
    for k, v in patch.model_dump(exclude_none=True).items():
        s[k] = v
    save_settings(s)
    return get_settings()


@router.get("/ollama/models")
async def list_ollama_models(url: str | None = None) -> dict:
    """List models installed in the configured (or given) Ollama server.

    Proxies ``GET {url}/api/tags`` so the UI can render a dropdown instead of
    a free-text field. Returns ``{"ok": bool, "models": [name, ...], "error": str?}``.
    """
    import httpx

    base = (url or load_settings().get("ollama_url") or "http://localhost:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{base}/api/tags")
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "models": [], "error": str(e), "url": base}
    models = [m.get("name") for m in data.get("models", []) if m.get("name")]
    models.sort()
    return {"ok": True, "models": models, "url": base}


async def _run_chat(req: ChatRequest) -> AsyncIterator[bytes]:
    settings = load_settings()
    if req.settings_override:
        settings = {**settings, **req.settings_override}

    try:
        provider = make_provider(settings)
    except Exception as e:
        yield _sse({"type": "error",
                    "message": f"LLM provider init failed: {e}"})
        return

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(req.messages)
    tools = tool_specs()

    # Track which messages to persist. The last message in req.messages is
    # the new user turn; everything the model/tools emit below is also new.
    persist = bool(req.persist and req.conversation_id)
    new_messages: list[dict] = []
    if persist and req.messages:
        last_user = req.messages[-1]
        if last_user.get("role") == "user":
            new_messages.append({
                "role": "user",
                "content": last_user.get("content", ""),
            })
            # Auto-title the conversation from the first user message.
            chat_store.set_title_if_empty(
                req.conversation_id or "",
                (last_user.get("content") or "").strip(),
            )

    try:
        max_turns = int(settings.get("max_tool_turns") or DEFAULT_MAX_TURNS)
    except (TypeError, ValueError):
        max_turns = DEFAULT_MAX_TURNS
    max_turns = max(MIN_MAX_TURNS, min(MAX_MAX_TURNS, max_turns))

    for _turn in range(max_turns):
        pending_tool_calls: list[dict] = []
        assistant_text_parts: list[str] = []

        try:
            async for evt in provider.chat_stream(messages, tools):
                if evt["type"] == "text":
                    assistant_text_parts.append(evt["text"])
                    yield _sse(evt)
                elif evt["type"] == "tool_call":
                    pending_tool_calls.append(evt)
                    yield _sse(evt)
                elif evt["type"] == "done":
                    break
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})
            if persist and new_messages:
                chat_store.append_messages(req.conversation_id, new_messages)
            return

        # Record assistant message in history.
        assistant_msg: dict = {
            "role": "assistant",
            "content": "".join(assistant_text_parts),
        }
        if pending_tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"], "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments") or {}),
                    },
                }
                for tc in pending_tool_calls
            ]
        messages.append(assistant_msg)
        new_messages.append(assistant_msg)

        if not pending_tool_calls:
            yield _sse({"type": "done"})
            if persist:
                chat_store.append_messages(req.conversation_id, new_messages)
            return

        # Execute each tool and append results.
        for tc in pending_tool_calls:
            result = dispatch(tc["name"], tc.get("arguments") or {})
            yield _sse({
                "type": "tool_result",
                "id": tc["id"],
                "name": tc["name"],
                "result": result,
            })
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "content": result,
            }
            messages.append(tool_msg)
            new_messages.append(tool_msg)

    yield _sse({"type": "error",
                "message": f"Exceeded {max_turns} tool turns."})
    yield _sse({"type": "done"})
    if persist and new_messages:
        chat_store.append_messages(req.conversation_id, new_messages)


def _sse(obj: dict) -> bytes:
    return ("data: " + json.dumps(obj) + "\n\n").encode("utf-8")


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_run_chat(req), media_type="text/event-stream")
