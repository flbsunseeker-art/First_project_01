"""Mutual-fund metadata and fixed daily-investment execution."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import threading

from apps.api.domain import ledger
from apps.api.repositories import storage


ZERO = Decimal("0")
_sync_lock = threading.Lock()


def classify_fund(name: str) -> str:
    normalized = name.upper()
    if "QDII-FOF" in normalized:
        return "QDII-FOF"
    if "QDII" in normalized:
        return "QDII"
    if "债券" in name:
        return "债券基金"
    if "指数" in name or "ETF联接" in normalized:
        return "指数基金"
    if "股票" in name:
        return "股票基金"
    if "混合" in name:
        return "混合基金"
    return "其他基金"


def upsert_plan(
    security_id: int,
    amount_cny,
    start_date: date | str,
    note: str = "",
    active: bool = True,
) -> int:
    amount = ledger.decimal(amount_cny)
    if amount <= ZERO:
        raise ledger.LedgerError("每日定投金额必须大于 0")
    day = ledger._iso_date(start_date)
    now = datetime.now().isoformat(timespec="seconds")
    storage.ensure_database()
    with storage.get_connection() as conn:
        security = conn.execute(
            "SELECT asset_type FROM securities WHERE id = ?", (security_id,)
        ).fetchone()
        if not security or security["asset_type"] != "MUTUAL_FUND":
            raise ledger.LedgerError("定投计划只能关联场外基金")
        conn.execute(
            """
            INSERT INTO fund_investment_plans
                (security_id, amount_cny, start_date, active, note,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(security_id) DO UPDATE SET
                amount_cny = excluded.amount_cny,
                start_date = excluded.start_date,
                active = excluded.active,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (
                security_id,
                str(amount),
                day,
                int(active),
                note.strip(),
                now,
                now,
            ),
        )
        plan_id = conn.execute(
            "SELECT id FROM fund_investment_plans WHERE security_id = ?",
            (security_id,),
        ).fetchone()["id"]
        conn.commit()
    return int(plan_id)


def list_plans(active_only: bool = False) -> list[dict]:
    storage.ensure_database()
    where = "WHERE p.active = 1" if active_only else ""
    with storage.get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT p.*, s.code, s.name, s.fund_category
            FROM fund_investment_plans p
            JOIN securities s ON s.id = p.security_id
            {where}
            ORDER BY s.code
            """
        ).fetchall()
    return [dict(row) for row in rows]


def sync_recurring_investments(refresh_navs: bool = True) -> dict:
    with _sync_lock:
        return _sync_recurring_investments(refresh_navs=refresh_navs)


def _sync_recurring_investments(refresh_navs: bool = True) -> dict:
    """Book one BUY per eligible weekday NAV once the plan can confirm it."""
    storage.ensure_database()
    plans = list_plans(active_only=True)
    if not plans:
        return {"created": 0, "earliest_date": None, "refresh_errors": []}

    refresh_errors: list[str] = []
    if refresh_navs:
        from apps.api.adapters import market_data

        securities = [ledger.get_security(plan["security_id"]) for plan in plans]
        try:
            refresh_errors = market_data.refresh_fund_navs(securities)
        except Exception as exc:
            refresh_errors = [str(exc)]

    created = 0
    earliest: str | None = None
    now = datetime.now().isoformat(timespec="seconds")
    today = date.today().isoformat()
    with storage.get_connection() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            for plan in conn.execute("SELECT * FROM fund_investment_plans WHERE active = 1"):
                prices = conn.execute(
                    """
                    WITH trading_navs AS (
                        SELECT price_date, close_price,
                               LEAD(price_date) OVER (ORDER BY price_date) AS next_nav_date
                        FROM market_prices
                        WHERE security_id = ? AND status = 'ok'
                          AND price_date BETWEEN ? AND ?
                          AND strftime('%w', price_date) BETWEEN '1' AND '5'
                    )
                    SELECT n.price_date, n.close_price,
                           CASE WHEN ? THEN n.next_nav_date ELSE n.price_date END AS effective_date
                    FROM trading_navs n
                    WHERE NOT EXISTS (
                        SELECT 1 FROM fund_plan_executions e
                        JOIN effective_trades t ON t.id = e.trade_id
                        WHERE e.plan_id = ? AND e.nav_date = n.price_date
                    )
                    ORDER BY n.price_date
                    """,
                    (
                        plan["security_id"], plan["start_date"], today,
                        plan["confirm_on_next_nav"], plan["id"],
                    ),
                ).fetchall()
                amount = Decimal(plan["amount_cny"])
                for price in prices:
                    nav = Decimal(price["close_price"])
                    effective_date = price["effective_date"]
                    if nav <= ZERO or effective_date is None:
                        continue
                    shares = amount / nav
                    sequence = ledger._next_sequence(conn, effective_date)
                    trade = conn.execute(
                        """
                        INSERT INTO trades
                            (security_id, trade_date, sequence, side, shares,
                             price, reason_category, note, created_at, updated_at)
                        VALUES (?, ?, ?, 'BUY', ?, ?, '定投计划', ?, ?, ?)
                        """,
                        (
                            plan["security_id"],
                            effective_date,
                            sequence,
                            str(shares),
                            str(nav),
                            f"自动定投 {amount} 元；净值日 {price['price_date']}",
                            now,
                            now,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO fund_plan_executions
                            (plan_id, security_id, nav_date, effective_date,
                             amount_cny, nav, shares, trade_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(plan_id, nav_date) DO UPDATE SET
                            effective_date = excluded.effective_date,
                            amount_cny = excluded.amount_cny,
                            nav = excluded.nav,
                            shares = excluded.shares,
                            trade_id = excluded.trade_id,
                            created_at = excluded.created_at
                        """,
                        (
                            plan["id"],
                            plan["security_id"],
                            price["price_date"],
                            effective_date,
                            str(amount),
                            str(nav),
                            str(shares),
                            trade.lastrowid,
                            now,
                        ),
                    )
                    created += 1
                    if earliest is None or effective_date < earliest:
                        earliest = effective_date
            if created:
                ledger._calculate_positions_conn(conn, today)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "created": created,
        "earliest_date": earliest,
        "refresh_errors": refresh_errors,
    }
