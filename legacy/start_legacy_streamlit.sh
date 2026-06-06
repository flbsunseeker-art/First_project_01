#!/usr/bin/env bash
set -euo pipefail

LEGACY_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$LEGACY_DIR/.." && pwd)"

cd "$ROOT_DIR"
echo "Deprecated: Streamlit is a legacy prototype. Use ./start.command for StockPilot."
PYTHONPATH="$ROOT_DIR:$LEGACY_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  streamlit run legacy/app.py --server.headless true
