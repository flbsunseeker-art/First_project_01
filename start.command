#!/usr/bin/env bash
set -euo pipefail
set -m

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEB_DIR="$ROOT_DIR/apps/web"
API_HOST="${STOCKPILOT_API_HOST:-127.0.0.1}"
API_PORT="${STOCKPILOT_API_PORT:-8000}"
WEB_HOST="${STOCKPILOT_WEB_HOST:-127.0.0.1}"
WEB_PORT="${STOCKPILOT_WEB_PORT:-3000}"
API_URL="http://${API_HOST}:${API_PORT}"
WEB_URL="http://${WEB_HOST}:${WEB_PORT}"
export STOCKPILOT_WEB_ORIGIN="$WEB_URL"
API_PID=""
WEB_PID=""

cd "$ROOT_DIR"

# Finder-launched .command files do not load the same PATH as an interactive
# shell. Add common Node locations before starting Next.js.
export PATH="$ROOT_DIR/.tools:$HOME/.local/node-current/bin:/opt/homebrew/bin:/usr/local/bin:/Applications/Codex.app/Contents/Resources:$PATH"

api_ready() {
  local response
  response="$(curl --noproxy '*' -fsS --max-time 3 "$API_URL/api/v1/health" 2>/dev/null)" &&
    [[ "$response" == *'"service":"stockpilot-api"'* ]]
}

web_ready() {
  local response
  response="$(curl --noproxy '*' -fsS --max-time 3 "$WEB_URL/api/health" 2>/dev/null)" &&
    [[ "$response" == *'"service":"stockpilot-web"'* ]]
}

web_build_needed() {
  local stamp=".next/.stockpilot-api-url" source
  if [[ ! -f .next/BUILD_ID || ! -f "$stamp" || "$(cat "$stamp")" != "$API_URL" ]]; then
    return 0
  fi
  for source in app components lib public package.json pnpm-lock.yaml next.config.mjs tsconfig.json \
    .env .env.local .env.production .env.production.local; do
    if [[ -e "$source" && -n "$(find "$source" -newer "$stamp" -print -quit)" ]]; then
      return 0
    fi
  done
  return 1
}

ensure_port_available() {
  if lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "端口 $1 已被占用，未能确认对应的 StockPilot 服务已就绪。" >&2
    exit 1
  fi
}

wait_until_ready() {
  local check="$1" pid="$2" label="$3"
  local deadline=$((SECONDS + 75))
  until "$check"; do
    if ! kill -0 "$pid" 2>/dev/null || (( SECONDS >= deadline )); then
      echo "$label 启动失败或超时，请查看上方日志。" >&2
      exit 1
    fi
    sleep 1
  done
}

has_backend_deps() {
  "$1" - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
import akshare
import jinja2
import pandas
import yfinance
PY
}

cleanup() {
  local pid
  # Job control gives each service its own process group, including workers.
  for pid in "$WEB_PID" "$API_PID"; do
    if [[ -n "$pid" ]]; then
      kill -TERM -- "-$pid" 2>/dev/null || true
    fi
  done
  wait || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if ! api_ready; then
  ensure_port_available "$API_PORT"
  if [[ -z "${PYTHON:-}" ]]; then
    PYTHON=python3
    if [[ -x "$ROOT_DIR/.venv/bin/python" ]] && has_backend_deps "$ROOT_DIR/.venv/bin/python"; then
      PYTHON="$ROOT_DIR/.venv/bin/python"
    fi
  fi
  if ! has_backend_deps "$PYTHON"; then
    echo "后端依赖缺失。请在项目目录运行 $PYTHON -m pip install -r requirements.txt" >&2
    exit 1
  fi
  echo "正在启动 StockPilot 后端…"
  api_args=(apps.api.main:app --host "$API_HOST" --port "$API_PORT")
  if [[ "${STOCKPILOT_DEV:-0}" == "1" ]]; then
    api_args+=(--reload)
  fi
  "$PYTHON" -m uvicorn "${api_args[@]}" &
  API_PID=$!
  wait_until_ready api_ready "$API_PID" "StockPilot 后端"
fi

if ! web_ready; then
  ensure_port_available "$WEB_PORT"
  if ! command -v node >/dev/null || ! command -v pnpm >/dev/null; then
    echo "找不到 Node.js 或 pnpm，请先安装前端运行环境。" >&2
    exit 1
  fi
  if [[ ! -x "$WEB_DIR/node_modules/.bin/next" ]]; then
    echo "前端依赖缺失。请在 apps/web 目录运行 pnpm install。" >&2
    exit 1
  fi
  echo "正在启动 StockPilot 前端…"
  (
    cd "$WEB_DIR"
    export NEXT_PUBLIC_API_BASE_URL="$API_URL"
    export pnpm_config_verify_deps_before_run=warn
    export NEXT_TELEMETRY_DISABLED=1
    if [[ "${STOCKPILOT_DEV:-0}" == "1" ]]; then
      exec pnpm run dev --hostname "$WEB_HOST" --port "$WEB_PORT"
    fi
    if web_build_needed; then
      echo "正在构建 StockPilot 前端…"
      pnpm run build
      printf '%s\n' "$API_URL" > .next/.stockpilot-api-url
    fi
    exec pnpm run start --hostname "$WEB_HOST" --port "$WEB_PORT"
  ) &
  WEB_PID=$!
  wait_until_ready web_ready "$WEB_PID" "StockPilot 前端"
fi

echo "StockPilot 已就绪：$WEB_URL"
if [[ "${STOCKPILOT_OPEN_BROWSER:-1}" != "0" ]] && ! open "$WEB_URL"; then
  echo "请在浏览器中手动打开上方网址。"
fi

if [[ -n "$API_PID" || -n "$WEB_PID" ]]; then
  echo "保持此窗口打开。按 Ctrl+C 停止本次启动的服务。"
  while [[ -z "$API_PID" ]] || kill -0 "$API_PID" 2>/dev/null; do
    if [[ -n "$WEB_PID" ]] && ! kill -0 "$WEB_PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  echo "StockPilot 服务已退出，请查看上方日志。" >&2
  exit 1
fi
