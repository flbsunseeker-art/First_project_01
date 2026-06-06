#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
echo "Deprecated: Streamlit is a legacy prototype. Use ./start.sh for StockPilot."
streamlit run app.py --server.headless true
