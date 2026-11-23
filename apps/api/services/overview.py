"""Lightweight overview service used by early FastAPI smoke tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

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


def get_snapshot_overview() -> dict:
    """Read the last complete close without initiating a market refresh."""
    metadata = get_overview_smoke()
    with storage.get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM daily_portfolio_snapshots
            WHERE status = 'ok' AND is_final = 1
            ORDER BY snapshot_date DESC LIMIT 1
            """
        ).fetchone()
    if row is None:
        return {**metadata, "status": "no_snapshot"}
    total = Decimal(row["total_market_value_cny"])
    unrealized = Decimal(row["unrealized_pnl_cny"])
    realized = Decimal(row["realized_pnl_cny"])
    cost = total - unrealized
    pnl = realized + unrealized
    return {
        **metadata,
        "status": "snapshot",
        "total_market_value_cny": total,
        "total_cost_cny": cost,
        "total_pnl_cny": pnl,
        "total_pnl_pct": pnl / cost * Decimal("100") if cost else None,
        "realized_pnl_cny": realized,
        "unrealized_pnl_cny": unrealized,
        "snapshot_date": row["snapshot_date"],
        "updated_at": row["calculated_at"],
    }


def valuation_overview(current: dict) -> dict:
    totals = {key: current[key] for key in (
        "total_market_value_cny", "total_cost_cny", "total_pnl_cny", "total_pnl_pct",
        "today_pnl_cny", "today_pnl_pct", "realized_pnl_cny", "unrealized_pnl_cny",
        "missing", "updated_at",
    )}
    asset_values = {"stocks": Decimal(0), "funds": Decimal(0)}
    dates = []
    for row in current["rows"]:
        asset_group = "funds" if row["asset_type"] == "MUTUAL_FUND" else "stocks"
        asset_values[asset_group] += row["market_value_cny"]
        if row.get("price_date"):
            dates.append(row["price_date"])
    return {
        **totals,
        "status": "ok",
        "valuation_date": date.today(),
        "asset_values": asset_values,
        "quote_from": min(dates, default=None),
        "quote_through": max(dates, default=None),
    }
