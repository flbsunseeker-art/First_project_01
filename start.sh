#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_HOST="${STOCKPILOT_API_HOST:-127.0.0.1}"
API_PORT="${STOCKPILOT_API_PORT:-8000}"
WEB_HOST="${STOCKPILOT_WEB_HOST:-127.0.0.1}"
WEB_PORT="${STOCKPILOT_WEB_PORT:-3000}"

cd "$ROOT_DIR"

# Finder-launched .command files do not load the same PATH as an interactive
# shell. Add common Node locations before starting Next.js.
export PATH="/Applications/Codex.app/Contents/Resources:/opt/homebrew/bin:/usr/local/bin:$ROOT_DIR/.tools:$PATH"

has_backend_deps() {
  "$1" - <<'PY' >/dev/null 2>&1
import fastapi
import pandas
import yfinance
PY
}

if [ -n "${PYTHON:-}" ]; then
  true
elif [ -x "$ROOT_DIR/.venv/bin/python" ] && has_backend_deps "$ROOT_DIR/.venv/bin/python"; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PYTHON="python3"
fi

if ! has_backend_deps "$PYTHON"; then
  echo "Missing backend dependencies for $PYTHON." >&2
  echo "Run: $PYTHON -m pip install -r requirements.txt" >&2
  exit 1
fi

if [ -x "$ROOT_DIR/.tools/pnpm" ]; then
  PNPM="$ROOT_DIR/.tools/pnpm"
elif command -v pnpm >/dev/null 2>&1; then
  PNPM="$(command -v pnpm)"
else
  echo "Missing pnpm. Install pnpm or keep project-local .tools/pnpm available." >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Missing node. Install Node.js, or run from a shell where node is available." >&2
  exit 1
fi

cleanup() {
  if [ -n "${API_PID:-}" ] && kill -0 "$API_PID" >/dev/null 2>&1; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "${WEB_PID:-}" ] && kill -0 "$WEB_PID" >/dev/null 2>&1; then
    kill "$WEB_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "Starting StockPilot API at http://${API_HOST}:${API_PORT}"
"$PYTHON" -m uvicorn apps.api.main:app \
  --host "$API_HOST" \
  --port "$API_PORT" \
  --reload &
API_PID=$!

echo "Starting StockPilot Web at http://${WEB_HOST}:${WEB_PORT}"
cd "$ROOT_DIR/apps/web"
NEXT_PUBLIC_API_BASE_URL="http://${API_HOST}:${API_PORT}" \
"$PNPM" run dev --hostname "$WEB_HOST" --port "$WEB_PORT" &
WEB_PID=$!

echo
echo "StockPilot is starting."
echo "Open: http://${WEB_HOST}:${WEB_PORT}"
echo "API:  http://${API_HOST}:${API_PORT}/api/v1/health"
echo
echo "Press Ctrl+C to stop both services."

wait "$API_PID" "$WEB_PID"
