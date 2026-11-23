#!/usr/bin/env python3
"""Import an external mutual-fund snapshot into the local StockPilot ledger."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from apps.api.domain import ledger
from apps.api.repositories import storage
from apps.api.services import funds, valuation


def _decimal(value) -> Decimal:
    return Decimal(str(value))


def _find_fund(code: str) -> dict | None:
    with storage.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM securities WHERE market = 'FUND' AND code = ?",
            (code,),
        ).fetchone()
    return dict(row) if row else None


def _upsert_nav(security_id: int, nav_date: str, nav: Decimal) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with storage.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO market_prices
                (security_id, price_date, close_price, source, status, fetched_at)
            VALUES (?, ?, ?, 'imported-fund-snapshot', 'ok', ?)
            ON CONFLICT(security_id, price_date) DO UPDATE SET
                close_price = excluded.close_price,
                source = excluded.source,
                status = excluded.status,
                fetched_at = excluded.fetched_at
            """,
            (security_id, nav_date, str(nav), now),
        )
        conn.commit()


def import_snapshot(
    source: Path, baseline_date: str | None = None, *, import_plans: bool = False
) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    snapshot_date = baseline_date or payload["snapshot"]["date"]
    storage.ensure_database()

    imported = 0
    confirmed_value = Decimal("0")
    cost_total = Decimal("0")
    security_ids: dict[str, int] = {}
    for item in payload.get("funds", []):
        code = str(item["fund_code"]).strip()
        name = str(item["fund_name"]).strip()
        category = funds.classify_fund(name)
        existing = _find_fund(code)
        if existing:
            security_id = int(existing["id"])
            with storage.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE securities
                    SET name = ?, asset_type = 'MUTUAL_FUND',
                        fund_category = ?, industry = '场外基金',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        name,
                        category,
                        datetime.now().isoformat(timespec="seconds"),
                        security_id,
                    ),
                )
                conn.commit()
        else:
            security_id = ledger.create_security(
                "FUND",
                code,
                name,
                industry="场外基金",
                asset_type="MUTUAL_FUND",
                fund_category=category,
            )

        shares = _decimal(item["shares"])
        nav = _decimal(item["nav"])
        cost_amount = _decimal(item["implied_cost_amount"])
        baseline_value = shares * nav
        ledger.upsert_opening_position(
            security_id,
            snapshot_date,
            shares,
            cost_amount,
            baseline_value_cny=baseline_value,
            source_note=(
                f"基金持仓快照 {snapshot_date}；展示持有金额 "
                f"{item['holding_amount']}；待确认金额未计入持仓"
            ),
        )
        _upsert_nav(security_id, str(item["nav_date"]), nav)
        security_ids[code] = security_id
        confirmed_value += baseline_value
        cost_total += cost_amount
        imported += 1

    plans = 0
    plan_items = payload.get("daily_invest_plans", []) if import_plans else []
    for item in plan_items:
        code = str(item["fund_code"]).strip()
        security_id = security_ids.get(code)
        if security_id is None:
            continue
        amount = item.get("actual_daily_amt")
        if amount is None:
            continue
        funds.upsert_plan(
            security_id,
            amount,
            str(item.get("next_deduct") or snapshot_date),
            note="每个已发布基金净值日按固定金额自动记账",
        )
        plans += 1

    valuation.invalidate_caches()
    return {
        "status": "ok",
        "snapshot_date": snapshot_date,
        "funds_imported": imported,
        "plans_imported": plans,
        "confirmed_value_cny": str(confirmed_value),
        "cost_total_cny": str(cost_total),
        "pending_amount_ignored_cny": str(
            sum(
                (_decimal(item.get("pending_amount", 0)) for item in payload["funds"]),
                Decimal("0"),
            )
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="基金持仓 JSON 文件")
    parser.add_argument(
        "--baseline-date",
        help="覆盖 JSON 中的快照日期，格式 YYYY-MM-DD",
    )
    parser.add_argument("--import-plans", action="store_true", help="显式启用文件中的定投计划")
    args = parser.parse_args()
    print(
        json.dumps(
            import_snapshot(args.source, args.baseline_date, import_plans=args.import_plans),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
