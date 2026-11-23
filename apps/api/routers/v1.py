"""Core StockPilot API routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel

from apps.api.domain import ledger
from apps.api.repositories import storage
from apps.api.services.overview import get_overview_smoke, get_snapshot_overview, valuation_overview


router = APIRouter(prefix="/api/v1")


class IndustryUpdate(BaseModel):
    industry: str


class TradePayload(BaseModel):
    security_id: int | None = None
    market: str | None = None
    code: str | None = None
    name: str | None = None
    currency: str | None = None
    industry: str = "其他"
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
def get_overview(snapshot_only: bool = False) -> dict:
    from apps.api.services import valuation

    current = None if snapshot_only else valuation.latest_current_valuation()
    if current and not current["missing"]:
        return _jsonable({**get_overview_smoke(), **valuation_overview(current)})
    return _jsonable(get_snapshot_overview())


@router.get("/holdings", tags=["portfolio"])
def get_holdings() -> list[dict]:
    return _jsonable(_current()["rows"])


@router.get("/holdings/summary", tags=["portfolio"])
def get_holdings_summary(cached_only: bool = False) -> dict:
    from apps.api.services import exposure, funds, valuation

    current = (
        valuation.latest_current_valuation() or valuation.current_valuation(cached_only=True)
        if cached_only else _current()
    )
    rows = current["rows"]
    price_dates = [row["price_date"] for row in rows if row.get("price_date")]
    return _jsonable(
        {
            "holdings": rows + current["unvalued"],
            **exposure.breakdown(rows),
            "investment_plans": funds.list_plans(active_only=True),
            "missing": current["missing"],
            "quote_from": min(price_dates, default=None),
            "quote_through": max(price_dates, default=None),
            "cached": cached_only,
        }
    )


@router.get("/holdings/allocation/industry", tags=["portfolio"])
def get_industry_allocation() -> list[dict]:
    from apps.api.services import exposure

    return _jsonable(exposure.breakdown(_current()["rows"])["industry"])


@router.get("/holdings/allocation/market", tags=["portfolio"])
def get_market_allocation() -> list[dict]:
    from apps.api.services import exposure

    return _jsonable(exposure.breakdown(_current()["rows"])["market"])


@router.patch("/securities/{security_id}/industry", tags=["portfolio"])
def patch_security_industry(security_id: int, payload: IndustryUpdate) -> dict:
    from apps.api.services import valuation

    try:
        ledger.update_security_industry(security_id, payload.industry)
        valuation.invalidate_caches()
        return _jsonable(ledger.get_security(security_id))
    except ledger.LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trades", tags=["trades"])
def get_trades() -> list[dict]:
    return _jsonable(ledger.list_trades())


@router.get("/securities", tags=["portfolio"])
def get_securities(active_only: bool = False) -> list[dict]:
    return _jsonable(ledger.list_securities(active_only=active_only))


@router.post("/trades", tags=["trades"], status_code=201)
def post_trade(payload: TradePayload) -> dict:
    from apps.api.services import valuation

    try:
        payload_data = _payload_dict(payload)
        security_id = payload_data.pop("security_id")
        market = payload_data.pop("market")
        code = payload_data.pop("code")
        name = payload_data.pop("name")
        currency = payload_data.pop("currency")
        industry = payload_data.pop("industry")
        if security_id is None:
            if not market or not code or not name:
                raise ledger.LedgerError("新股票需要填写市场、代码和名称")
            expected_currency = ledger.CURRENCY_BY_MARKET.get(market.strip().upper())
            if currency and expected_currency and currency != expected_currency:
                raise ledger.LedgerError("币种需要与所属市场匹配")
            security_id = ledger.create_security(
                market=market,
                code=code,
                name=name,
                industry=industry,
            )
        trade_id = ledger.record_trade(security_id=security_id, **payload_data)
        valuation.rebuild_from(payload.trade_date)
        valuation.invalidate_caches()
        return {"id": trade_id, "status": "ok"}
    except ledger.LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/trades/{trade_id}", tags=["trades"])
def patch_trade(trade_id: int, payload: TradePayload) -> dict:
    from apps.api.services import valuation

    try:
        payload_data = _payload_dict(payload)
        security_id = payload_data.pop("security_id")
        payload_data.pop("market")
        payload_data.pop("code")
        payload_data.pop("name")
        payload_data.pop("currency")
        payload_data.pop("industry")
        if security_id is None:
            raise ledger.LedgerError("交易修改需要指定已有股票")
        ledger.update_trade(trade_id=trade_id, **payload_data)
        valuation.rebuild_from(payload.trade_date)
        valuation.invalidate_caches()
        return {"id": trade_id, "status": "ok"}
    except ledger.LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/trades/{trade_id}", tags=["trades"])
def delete_trade(trade_id: int) -> dict:
    from apps.api.services import valuation

    ledger.delete_trade(trade_id)
    valuation.rebuild_from(date.today())
    valuation.invalidate_caches()
    return {"id": trade_id, "status": "ok"}


@router.get("/analytics/daily-returns", tags=["analytics"])
def get_daily_returns(start_date: date | None = None, end_date: date | None = None) -> list[dict]:
    from apps.api.services import valuation

    valuation.auto_backfill()
    return _jsonable(valuation.get_daily_returns(start_date, end_date))


@router.get("/analytics/performance", tags=["analytics"])
def get_performance(calendar: bool = False) -> dict:
    from apps.api.services import performance

    return _jsonable(performance.history(calendar=calendar))


@router.get("/analytics/benchmarks", tags=["analytics"])
def get_benchmark_comparison() -> dict:
    from apps.api.services import benchmarks, performance

    return _jsonable(benchmarks.get_comparison(performance.history()))


@router.get("/analytics/snapshots/{snapshot_date}", tags=["analytics"])
def get_snapshot(snapshot_date: date) -> list[dict]:
    from apps.api.services import valuation

    return _jsonable(valuation.get_snapshot_details(snapshot_date))


@router.get("/analytics/value-trend", tags=["analytics"])
def get_value_trend(
    start_date: date | None = None,
    end_date: date | None = None,
    asset_group: str = "all",
    snapshot_only: bool = False,
) -> list[dict]:
    from apps.api.services import valuation

    if not snapshot_only:
        valuation.auto_backfill()
    if asset_group in {"stocks", "funds"}:
        rows = valuation.get_asset_value_trend(asset_group, start_date, end_date)
        if snapshot_only:
            return _jsonable(rows)
        current_day = date.today().isoformat()
        include_today = (start_date is None or date.today() >= start_date) and (
            end_date is None or date.today() <= end_date
        )
        if include_today:
            current = _current()
            value = sum(
                (
                    row["market_value_cny"]
                    for row in current["rows"]
                    if (row["asset_type"] == "MUTUAL_FUND")
                    == (asset_group == "funds")
                ),
                Decimal("0"),
            )
            current_row = {
                "snapshot_date": current_day,
                "total_market_value_cny": value,
                "cumulative_pnl_cny": Decimal("0"),
                "daily_pnl_cny": None,
                "status": "live",
            }
            if rows and rows[-1]["snapshot_date"] == current_day:
                rows[-1] = current_row
            elif value > 0:
                rows.append(current_row)
        return _jsonable(rows)
    if asset_group != "all":
        raise HTTPException(status_code=400, detail="asset_group 仅支持 all、stocks、funds")
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


@router.get("/data/refresh", tags=["data"])
def get_market_refresh() -> dict:
    from apps.api.services import market_refresh

    return _jsonable(market_refresh.status())


@router.post("/data/refresh", tags=["data"], status_code=202)
def post_market_refresh() -> dict:
    from apps.api.services import market_refresh

    return _jsonable(market_refresh.start())


@router.get("/data/status", tags=["data"])
def get_data_status() -> dict:
    storage.ensure_database()
    with storage.get_connection() as conn:
        latest_snapshot = conn.execute(
            """
            SELECT snapshot_date, status, is_final, error_message, calculated_at
            FROM daily_portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
            """
        ).fetchone()
        complete_through = conn.execute(
            """SELECT MAX(snapshot_date) FROM daily_portfolio_snapshots
               WHERE status = 'ok' AND is_final = 1"""
        ).fetchone()[0]
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
        "complete_snapshot_through": complete_through,
        "latest_sync": dict(latest_sync) if latest_sync else None,
    }


@router.post("/data/backfill", tags=["data"])
def post_backfill(payload: BackfillPayload) -> dict:
    from apps.api.services import valuation

    result = valuation.backfill_snapshots(payload.start_date, payload.end_date)
    valuation.invalidate_caches()
    return _jsonable(result)


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


@router.get("/research/weekly", include_in_schema=False)
def weekly_review() -> RedirectResponse:
    return RedirectResponse("/api/v1/research/diagnosis")


@router.get("/research/diagnosis", tags=["research"])
def get_diagnosis(cutoff: date | None = None) -> dict:
    from apps.api.services import diagnosis

    try:
        return diagnosis.read_report(cutoff)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
