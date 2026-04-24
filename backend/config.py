"""Runtime configuration for the backend.

The source-export path (where the user's Epic MyChart export lives) is
stored in ``data/settings.json`` so the user can configure it from the UI
without needing env vars. Env vars still win if set, which keeps the CLI
ergonomic on servers / CI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

APP_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal ``.env`` loader — no dependency on python-dotenv.

    Parses ``KEY=VALUE`` lines, ignores blanks and ``#`` comments, strips one
    layer of matching single/double quotes. Existing env vars win so an
    explicit ``export FOO=...`` or shell override is never clobbered.
    """
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            os.environ[key] = value
    except OSError:
        pass


# Load .env from the repo root before any other module reads os.environ.
_load_dotenv(APP_DIR / ".env")

DATA_DIR = APP_DIR / "data"
DB_PATH = Path(os.environ.get("MYCHART_DB", DATA_DIR / "mychart.db"))
SCHEMA_JSON_PATH = Path(
    os.environ.get("MYCHART_SCHEMA_JSON", DATA_DIR / "schema.json")
)
SETTINGS_PATH = DATA_DIR / "settings.json"

_DEFAULT_SETTINGS = {
    "llm_provider": "ollama",  # ollama | openai | anthropic | openrouter
    "ollama_model": "qwen3.5:latest",
    "ollama_url": "http://localhost:11434",
    "openai_model": "gpt-4o-mini",
    "anthropic_model": "claude-3-5-sonnet-latest",
    "openrouter_model": "openai/gpt-4o-mini",
    "openrouter_url": "",  # blank = use https://openrouter.ai/api/v1
    "max_tool_turns": 20,  # cap on tool-calling loop iterations per chat turn
    "source_dir": "",  # set via UI or MYCHART_SOURCE env var
}


def load_settings() -> dict:
    settings = dict(_DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            settings.update(
                json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            )
        except json.JSONDecodeError:
            pass
    return settings


def save_settings(settings: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings, indent=2), encoding="utf-8"
    )
    try:
        os.chmod(SETTINGS_PATH, 0o600)
    except OSError:
        pass


def get_source_dir() -> Optional[Path]:
    """Return the user-configured Epic export root, or ``None`` if unset.

    Resolution order: ``MYCHART_SOURCE`` env var > settings.json > None.
    """
    env = os.environ.get("MYCHART_SOURCE")
    if env:
        return Path(env).expanduser()
    cfg = (load_settings().get("source_dir") or "").strip()
    if cfg:
        return Path(cfg).expanduser()
    return None
