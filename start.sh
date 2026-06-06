#!/bin/bash
cd "$(dirname "$0")"
echo "Deprecated: Streamlit is a legacy prototype. Use FastAPI + Next.js for StockPilot."
streamlit run app.py --server.headless true
