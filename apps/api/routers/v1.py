"""Core StockPilot API routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from apps.api.domain import ledger
from apps.api.repositories import storage
from apps.api.services.overview import get_overview_smoke


router = APIRouter(prefix="/api/v1")


class IndustryUpdate(BaseModel):
    industry: str


class TradePayload(BaseModel):
    security_id: int
    trade_date: date
    side: str
    shares: Decimal
    price: Decimal
    reason_category: str = ""
    note: str = ""


class BackfillPayload(BaseModel):
    start_date: date
    end_date: date


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _current() -> dict:
    from apps.api.services import valuation

    try:
        return valuation.current_valuation()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _payload_dict(payload: BaseModel) -> dict:
    return payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()


@router.get("/overview", tags=["portfolio"])
def get_overview() -> dict:
    current = _current()
    return _jsonable(
        {
            **get_overview_smoke(),
            "total_market_value_cny": current["total_market_value_cny"],
            "total_cost_cny": current["total_cost_cny"],
            "total_pnl_cny": current["total_pnl_cny"],
            "today_pnl_cny": current["today_pnl_cny"],
            "realized_pnl_cny": current["realized_pnl_cny"],
            "unrealized_pnl_cny": current["unrealized_pnl_cny"],
            "missing": current["missing"],
            "updated_at": current["updated_at"],
        }
    )


@router.get("/holdings", tags=["portfolio"])
def get_holdings() -> list[dict]:
    return _jsonable(_current()["rows"])


@router.get("/holdings/allocation/industry", tags=["portfolio"])
def get_industry_allocation() -> list[dict]:
    from apps.api.services import valuation

    current = _current()
    return _jsonable(valuation.get_industry_allocation(current["rows"]))


@router.get("/holdings/allocation/market", tags=["portfolio"])
def get_market_allocation() -> list[dict]:
    rows = _current()["rows"]
    grouped: dict[str, Decimal] = {}
    total = sum((row["market_value_cny"] for row in rows), Decimal("0"))
    for row in rows:
        market = row["market"]
        grouped[market] = grouped.get(market, Decimal("0")) + row["market_value_cny"]
    return _jsonable(
        [
            {
                "market": market,
                "market_value_cny": value,
                "position_pct": value / total * Decimal("100") if total else Decimal("0"),
            }
            for market, value in sorted(grouped.items())
        ]
    )


@router.patch("/securities/{security_id}/industry", tags=["portfolio"])
def patch_security_industry(security_id: int, payload: IndustryUpdate) -> dict:
    try:
        ledger.update_security_industry(security_id, payload.industry)
        return _jsonable(ledger.get_security(security_id))
    except ledger.LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trades", tags=["trades"])
def get_trades() -> list[dict]:
    return _jsonable(ledger.list_trades())


@router.post("/trades", tags=["trades"], status_code=201)
def post_trade(payload: TradePayload) -> dict:
    from apps.api.services import valuation

    try:
        trade_id = ledger.record_trade(**_payload_dict(payload))
        valuation.rebuild_from(payload.trade_date)
        return {"id": trade_id, "status": "ok"}
    except ledger.LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/trades/{trade_id}", tags=["trades"])
def patch_trade(trade_id: int, payload: TradePayload) -> dict:
    from apps.api.services import valuation

    try:
        ledger.update_trade(trade_id=trade_id, **_payload_dict(payload))
        valuation.rebuild_from(payload.trade_date)
        return {"id": trade_id, "status": "ok"}
    except ledger.LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/trades/{trade_id}", tags=["trades"])
def delete_trade(trade_id: int) -> dict:
    from apps.api.services import valuation

    ledger.delete_trade(trade_id)
    valuation.rebuild_from(date.today())
    return {"id": trade_id, "status": "ok"}


@router.get("/analytics/daily-returns", tags=["analytics"])
def get_daily_returns(start_date: date | None = None, end_date: date | None = None) -> list[dict]:
    from apps.api.services import valuation

    return _jsonable(valuation.get_daily_returns(start_date, end_date))


@router.get("/analytics/snapshots/{snapshot_date}", tags=["analytics"])
def get_snapshot(snapshot_date: date) -> list[dict]:
    from apps.api.services import valuation

    return _jsonable(valuation.get_snapshot_details(snapshot_date))


@router.get("/analytics/value-trend", tags=["analytics"])
def get_value_trend(start_date: date | None = None, end_date: date | None = None) -> list[dict]:
    from apps.api.services import valuation

    rows = valuation.get_daily_returns(start_date, end_date)
    return _jsonable(
        [
            {
                "snapshot_date": row["snapshot_date"],
                "total_market_value_cny": row["total_market_value_cny"],
                "cumulative_pnl_cny": row["cumulative_pnl_cny"],
                "daily_pnl_cny": row["daily_pnl_cny"],
                "status": row["status"],
            }
            for row in rows
        ]
    )


@router.get("/data/status", tags=["data"])
def get_data_status() -> dict:
    storage.ensure_database()
    with storage.get_connection() as conn:
        latest_snapshot = conn.execute(
            """
            SELECT snapshot_date, status, error_message, calculated_at
            FROM daily_portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
            """
        ).fetchone()
        latest_sync = conn.execute(
            """
            SELECT started_at, finished_at, start_date, end_date, status, details
            FROM sync_runs ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
    return {
        "status": "ok",
        "schema_version": storage.get_setting("schema_version"),
        "database": str(storage.DB_FILE),
        "latest_snapshot": dict(latest_snapshot) if latest_snapshot else None,
        "latest_sync": dict(latest_sync) if latest_sync else None,
    }


@router.post("/data/backfill", tags=["data"])
def post_backfill(payload: BackfillPayload) -> dict:
    from apps.api.services import valuation

    return _jsonable(valuation.backfill_snapshots(payload.start_date, payload.end_date))


@router.post("/data/backup", tags=["data"])
def post_backup() -> dict:
    path = storage.create_backup("api")
    return {"status": "ok", "path": str(path)}


@router.get("/trades/export.csv", tags=["trades"])
def export_trades_csv() -> PlainTextResponse:
    from apps.api.services.csv_io import export_trades_csv

    return PlainTextResponse(
        export_trades_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=stockpilot-trades.csv"},
    )


@router.post("/trades/import.csv", tags=["trades"])
def import_trades_csv(content: str = Body(..., media_type="text/csv")) -> dict:
    from apps.api.services.csv_io import import_trades_csv
    from apps.api.services import valuation

    result = import_trades_csv(content)
    valuation.rebuild_from(result["earliest_date"] or date.today())
    return result


@router.get("/report/html", tags=["data"])
def get_html_report() -> FileResponse:
    from apps.api.services import report

    path = Path(report.generate_report())
    return FileResponse(path, media_type="text/html", filename=path.name)
