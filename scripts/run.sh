#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." &> /dev/null && pwd )"

export PYTHONPATH="$PYTHONPATH:$REPO_ROOT/src"

PYTHON_BIN="python3"
if [ -f "$REPO_ROOT/.venv/Scripts/activate" ]; then
    source "$REPO_ROOT/.venv/Scripts/activate"
    PYTHON_BIN="$REPO_ROOT/.venv/Scripts/python.exe"
elif [ -f "$REPO_ROOT/.venv/bin/activate" ]; then
    source "$REPO_ROOT/.venv/bin/activate"
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
fi

if [ -f "$REPO_ROOT/.env" ]; then
    echo "Loading environment from .env..."
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

OPS_AGENT_PORT="${OPS_AGENT_PORT:-8000}"
export OPS_AGENT_PORT
OPS_AGENT_HOST="${OPS_AGENT_HOST:-127.0.0.1}"
export OPS_AGENT_HOST
if [ -z "${OPS_AGENT_AUTH_DISABLED:-}" ] && { [ "$OPS_AGENT_HOST" = "127.0.0.1" ] || [ "$OPS_AGENT_HOST" = "localhost" ]; }; then
    export OPS_AGENT_AUTH_DISABLED="true"
fi
export VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://127.0.0.1:${OPS_AGENT_PORT}}"

echo "Stopping processes on ports ${OPS_AGENT_PORT} and 5173..."
if command -v lsof >/dev/null 2>&1; then
    lsof -ti:"${OPS_AGENT_PORT}",5173 | xargs kill -9 2>/dev/null || true
elif command -v netstat >/dev/null 2>&1 && command -v taskkill >/dev/null 2>&1; then
    for port in "$OPS_AGENT_PORT" 5173; do
        netstat -ano | awk -v port=":$port" '$0 ~ port {print $5}' | sort -u | while read -r pid; do
            if [ -n "$pid" ] && [ "$pid" != "0" ]; then
                taskkill //F //PID "$pid" >/dev/null 2>&1 || true
            fi
        done
    done
fi

# Function to stop background processes on exit
cleanup() {
    echo "Stopping servers..."
    local jobs_pids
    jobs_pids=$(jobs -p)
    if [ -n "$jobs_pids" ]; then
        kill $jobs_pids 2>/dev/null || true
    fi
    exit
}

trap cleanup SIGINT SIGTERM

echo "Starting Ops Agent Backend..."
"$PYTHON_BIN" "$REPO_ROOT/src/app/main.py" &

echo "Starting Ops Agent Frontend..."
echo "Frontend API proxy target: ${VITE_API_PROXY_TARGET}"
cd "$REPO_ROOT/web" && pnpm dev &

# Wait for background processes
wait
