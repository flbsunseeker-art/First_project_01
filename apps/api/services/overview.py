"""Lightweight overview service used by early FastAPI smoke tests."""

from __future__ import annotations

from apps.api.core.config import settings
from apps.api.domain import ledger
from apps.api.repositories import storage


def get_overview_smoke() -> dict:
    """Return cheap portfolio metadata without fetching live market data."""
    storage.ensure_database()
    securities = ledger.list_securities()
    with storage.get_connection() as conn:
        row = conn.execute(
            """
            SELECT snapshot_date, total_market_value_cny, status, calculated_at
            FROM daily_portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
            """
        ).fetchone()
    latest_snapshot = dict(row) if row else None
    return {
        "status": "ok",
        "security_count": len(securities),
        "latest_snapshot": latest_snapshot,
        "database": str(storage.DB_FILE),
        "offline_mode": settings.offline_mode,
    }
