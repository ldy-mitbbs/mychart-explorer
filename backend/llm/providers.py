"""LLM provider abstraction.

Each provider accepts OpenAI-style chat messages + a tool spec and yields
events in a normalised shape:

    {"type": "text",  "text": "..."}          # incremental assistant text
    {"type": "tool_call", "id": "...",
     "name": "...", "arguments": <dict>}       # complete tool call
    {"type": "done"}

We keep the shape deliberately minimal so the chat loop can be provider-
agnostic.
"""

from __future__ import annotations

import json
import os
from typing import AsyncIterator, Protocol

import httpx


class LLMProvider(Protocol):
    name: str

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[dict]:
        ...


# --- Ollama ------------------------------------------------------------------

class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def chat_stream(self, messages, tools):
        """Ollama's /api/chat supports OpenAI-style tool specs.

        We stream newline-delimited JSON events. Tool calls arrive in a
        completed `message.tool_calls` list on a non-streaming (or terminal)
        response. Ollama does not emit tool_calls incrementally, so we collect
        everything and yield at the end for tool turns.
        """
        url = f"{self.base_url}/api/chat"
        # Ollama expects tool_calls[].function.arguments as an object, not a
        # JSON string, and does not accept the OpenAI-style `type` field on
        # tool_calls. Normalise the history before sending.
        norm: list[dict] = []
        for m in messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                tcs = []
                for tc in m["tool_calls"]:
                    fn = tc.get("function") or {}
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    tcs.append({"function": {
                        "name": fn.get("name"),
                        "arguments": args or {},
                    }})
                norm.append({
                    "role": "assistant",
                    "content": m.get("content") or "",
                    "tool_calls": tcs,
                })
            elif m.get("role") == "tool":
                norm.append({
                    "role": "tool",
                    "content": m.get("content") or "",
                })
            else:
                norm.append({
                    "role": m["role"],
                    "content": m.get("content") or "",
                })

        payload = {
            "model": self.model,
            "messages": norm,
            "stream": True,
            "options": {"temperature": 0.2},
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise RuntimeError(
                        f"Ollama {resp.status_code}: {body[:500]}"
                    )
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = chunk.get("message") or {}
                    thinking = msg.get("thinking") or ""
                    if thinking:
                        yield {"type": "reasoning", "text": thinking}
                    content = msg.get("content") or ""
                    if content:
                        yield {"type": "text", "text": content}
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        args = fn.get("arguments")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        yield {
                            "type": "tool_call",
                            "id": tc.get("id") or fn.get("name", "tc"),
                            "name": fn.get("name"),
                            "arguments": args or {},
                        }
                    if chunk.get("done"):
                        yield {"type": "done"}
                        return


# --- OpenAI ------------------------------------------------------------------

class OpenAIProvider:
    name = "openai"
    base_url = "https://api.openai.com/v1"
    env_key = "OPENAI_API_KEY"
    extra_headers: dict[str, str] = {}

    def __init__(self, model: str, api_key: str | None = None,
                 base_url: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ.get(self.env_key)
        if not self.api_key:
            raise RuntimeError(f"{self.env_key} not set")
        if base_url:
            self.base_url = base_url.rstrip("/")

    async def chat_stream(self, messages, tools):
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        tool_accum: dict[int, dict] = {}  # index -> {"id","name","args_str"}
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload,
                                     headers=headers) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise RuntimeError(
                        f"{self.name} {resp.status_code} at {url}: "
                        f"model={self.model!r}: {body[:800]}"
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        evt = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (evt.get("choices") or [{}])[0].get("delta") or {}
                    # Reasoning models (DeepSeek R1, OpenRouter passthrough,
                    # some OpenAI o-series) surface chain-of-thought via one
                    # of these fields. Names vary by provider/model.
                    reasoning = (
                        delta.get("reasoning")
                        or delta.get("reasoning_content")
                    )
                    if reasoning:
                        yield {"type": "reasoning", "text": reasoning}
                    if delta.get("content"):
                        yield {"type": "text", "text": delta["content"]}
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        slot = tool_accum.setdefault(idx, {
                            "id": None, "name": None, "args_str": ""
                        })
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = fn["name"]
                        if fn.get("arguments"):
                            slot["args_str"] += fn["arguments"]
        for slot in tool_accum.values():
            try:
                args = json.loads(slot["args_str"] or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_call", "id": slot["id"] or "tc",
                   "name": slot["name"], "arguments": args}
        yield {"type": "done"}


# --- OpenRouter (OpenAI-compatible) ----------------------------------------

class OpenRouterProvider(OpenAIProvider):
    """OpenRouter uses the OpenAI chat-completions wire format, so we reuse
    :class:`OpenAIProvider` and only override endpoint / key / headers.

    The ``model`` field is a fully-qualified OpenRouter model slug, e.g.
    ``anthropic/claude-3.5-sonnet`` or ``openai/gpt-4o-mini``.
    """

    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    env_key = "OPENROUTER_API_KEY"
    extra_headers = {
        # Optional attribution headers recommended by OpenRouter; harmless if
        # the app isn't public. Kept static to avoid leaking host info.
        "HTTP-Referer": "http://127.0.0.1",
        "X-Title": "mychart-explorer",
    }


# --- Anthropic --------------------------------------------------------------

class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

    async def chat_stream(self, messages, tools):
        # Anthropic uses a distinct "system" parameter.
        system = ""
        anth_messages: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                system += (m.get("content") or "") + "\n"
                continue
            if m["role"] == "tool":
                anth_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id", ""),
                        "content": m.get("content", ""),
                    }],
                })
                continue
            if m["role"] == "assistant" and m.get("tool_calls"):
                blocks: list[dict] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    fn = tc.get("function") or {}
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    blocks.append({
                        "type": "tool_use", "id": tc["id"],
                        "name": fn.get("name"),
                        "input": args or {},
                    })
                anth_messages.append({"role": "assistant", "content": blocks})
                continue
            anth_messages.append({
                "role": m["role"],
                "content": m.get("content", ""),
            })

        anth_tools = []
        for t in tools or []:
            fn = t.get("function") or {}
            anth_tools.append({
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object"}),
            })

        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system.strip(),
            "messages": anth_messages,
            "tools": anth_tools,
            "stream": True,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload,
                                     headers=headers) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise RuntimeError(
                        f"anthropic {resp.status_code}: "
                        f"model={self.model!r}: {body[:800]}"
                    )
                current_tool: dict | None = None
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    try:
                        evt = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    etype = evt.get("type")
                    if etype == "content_block_start":
                        block = evt.get("content_block") or {}
                        if block.get("type") == "tool_use":
                            current_tool = {"id": block.get("id"),
                                            "name": block.get("name"),
                                            "args_str": ""}
                    elif etype == "content_block_delta":
                        delta = evt.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            yield {"type": "text", "text": delta.get("text", "")}
                        elif delta.get("type") == "thinking_delta":
                            yield {"type": "reasoning",
                                   "text": delta.get("thinking", "")}
                        elif delta.get("type") == "input_json_delta" \
                                and current_tool is not None:
                            current_tool["args_str"] += delta.get("partial_json", "")
                    elif etype == "content_block_stop" and current_tool:
                        try:
                            args = json.loads(current_tool["args_str"] or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        yield {"type": "tool_call",
                               "id": current_tool["id"],
                               "name": current_tool["name"],
                               "arguments": args}
                        current_tool = None
                    elif etype == "message_stop":
                        break
        yield {"type": "done"}


# --- Factory -----------------------------------------------------------------

def make_provider(settings: dict) -> LLMProvider:
    name = settings.get("llm_provider", "ollama")
    if name == "ollama":
        return OllamaProvider(
            model=settings.get("ollama_model", "qwen3.5:latest"),
            base_url=settings.get("ollama_url", "http://localhost:11434"),
        )
    if name == "openai":
        return OpenAIProvider(
            model=settings.get("openai_model", "gpt-4o-mini"),
        )
    if name == "openrouter":
        return OpenRouterProvider(
            model=settings.get("openrouter_model",
                               "openai/gpt-4o-mini"),
            base_url=settings.get("openrouter_url") or None,
        )
    if name == "anthropic":
        return AnthropicProvider(
            model=settings.get("anthropic_model",
                               "claude-3-5-sonnet-latest"),
        )
    raise ValueError(f"Unknown provider: {name}")
