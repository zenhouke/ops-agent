#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
export OPS_AGENT_PORT="${OPS_AGENT_PORT:-${OPS_AGENT_BACKEND_PORT:-8000}}"

exec python3 src/app/main.py
