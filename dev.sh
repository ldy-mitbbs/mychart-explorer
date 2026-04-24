#!/usr/bin/env bash
# Start backend (uvicorn on 127.0.0.1:8765) and frontend (Vite on :5173)
# together. Ctrl+C stops both. Logs are interleaved with [backend]/[frontend]
# prefixes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Activate venv if present and not already active.
if [[ -z "${VIRTUAL_ENV:-}" && -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if ! command -v uvicorn >/dev/null 2>&1; then
  echo "uvicorn not found. Run: pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "[frontend] installing npm deps..."
  (cd frontend && npm install)
fi

pids=()
cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Prefix each line of a stream with a tag.
prefix() { sed -u "s/^/[$1] /"; }

uvicorn backend.main:app --host 127.0.0.1 --port 8765 2>&1 | prefix backend &
pids+=($!)

(cd frontend && npm run dev) 2>&1 | prefix frontend &
pids+=($!)

wait -n
# If one exits, take down the other.
cleanup
