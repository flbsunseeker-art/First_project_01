"""Portfolio valuation, daily snapshots, and historical backfill."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from apps.api.domain import ledger
from apps.api.repositories import storage


ZERO = Decimal("0")
CURRENT_CACHE_TTL_SECONDS = 15
BACKFILL_CACHE_TTL_SECONDS = 30
_current_cache: tuple[float, dict] | None = None
_backfill_checked_at = 0.0


def invalidate_caches() -> None:
    global _current_cache, _backfill_checked_at
    _current_cache = None
    _backfill_checked_at = 0.0


def _market_data():
    from apps.api.adapters import market_data

    return market_data


def _days(start: date, end: date):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def _securities_by_id() -> dict[int, dict]:
    return {item["id"]: item for item in ledger.list_securities()}


def _trade_flows(day: date) -> tuple[Decimal, Decimal]:
    market_data = _market_data()
    buy = ZERO
    sell = ZERO
    with storage.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT t.side, t.shares, t.price, s.currency
            FROM trades t JOIN securities s ON s.id = t.security_id
            WHERE t.trade_date = ?
            """,
            (day.isoformat(),),
        ).fetchall()
    for row in rows:
        rate = market_data.get_cached_rate(row["currency"], day)
        if rate is None:
            raise market_data.MarketDataError(
                f"{day.isoformat()} 缺少 {row['currency']}/CNY 汇率"
            )
        amount = Decimal(row["shares"]) * Decimal(row["price"]) * rate
        if row["side"] == "BUY":
            buy += amount
        else:
            sell += amount
    return buy, sell


def _realized_pnl_cny(day: date) -> Decimal:
    market_data = _market_data()
    total = ZERO
    for event in ledger.realized_events(day):
        rate = market_data.get_cached_rate(event["currency"], event["trade_date"])
        if rate is None:
            raise market_data.MarketDataError(
                f"{event['trade_date']} 缺少 {event['currency']}/CNY 汇率"
            )
        total += event["realized_pnl_native"] * rate
    return total


def _previous_valid_snapshot(day: date) -> dict | None:
    with storage.get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM daily_portfolio_snapshots
            WHERE snapshot_date < ? AND status = 'ok'
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (day.isoformat(),),
        ).fetchone()
    return dict(row) if row else None


def _has_valuation_activity(day: date) -> bool:
    positions = ledger.calculate_positions(day)
    held_ids = [
        security_id
        for security_id, position in positions.items()
        if position.shares > ZERO
    ]
    with storage.get_connection() as conn:
        trade = conn.execute(
            "SELECT 1 FROM trades WHERE trade_date = ? LIMIT 1",
            (day.isoformat(),),
        ).fetchone()
        if trade:
            return True
        if not held_ids:
            return False
        placeholders = ",".join("?" for _ in held_ids)
        quote = conn.execute(
            f"""
            SELECT 1 FROM market_prices
            WHERE price_date = ? AND security_id IN ({placeholders})
            LIMIT 1
            """,
            [day.isoformat(), *held_ids],
        ).fetchone()
    return quote is not None


def value_portfolio(valuation_date: date) -> dict:
    market_data = _market_data()
    securities = _securities_by_id()
    positions = ledger.calculate_positions(valuation_date)
    details = []
    total_value = ZERO
    total_cost = ZERO
    unrealized = ZERO

    for security_id, position in positions.items():
        if position.shares <= ZERO:
            continue
        security = securities[security_id]
        close = market_data.get_cached_price(security_id, valuation_date)
        rate = market_data.get_cached_rate(security["currency"], valuation_date)
        if close is None:
            raise market_data.MarketDataError(
                f"{valuation_date.isoformat()} 缺少 {security['name']} 行情"
            )
        if rate is None:
            raise market_data.MarketDataError(
                f"{valuation_date.isoformat()} 缺少 {security['currency']}/CNY 汇率"
            )
        market_value = position.shares * close * rate
        cost_value = position.shares * position.average_cost * rate
        pnl = market_value - cost_value
        details.append(
            {
                "security_id": security_id,
                "shares": position.shares,
                "average_cost": position.average_cost,
                "close_price": close,
                "cny_rate": rate,
                "market_value_cny": market_value,
                "cost_value_cny": cost_value,
                "unrealized_pnl_cny": pnl,
            }
        )
        total_value += market_value
        total_cost += cost_value
        unrealized += pnl

    realized = _realized_pnl_cny(valuation_date)
    buy_flow, sell_flow = _trade_flows(valuation_date)
    previous = _previous_valid_snapshot(valuation_date)
    if previous is None:
        daily_pnl = None
        cumulative = ZERO
    else:
        daily_pnl = (
            total_value
            - Decimal(previous["total_market_value_cny"])
            - buy_flow
            + sell_flow
        )
        cumulative = Decimal(previous["cumulative_pnl_cny"]) + daily_pnl

    return {
        "date": valuation_date.isoformat(),
        "details": details,
        "total_market_value_cny": total_value,
        "total_cost_cny": total_cost,
        "daily_pnl_cny": daily_pnl,
        "cumulative_pnl_cny": cumulative,
        "realized_pnl_cny": realized,
        "unrealized_pnl_cny": unrealized,
        "buy_flow_cny": buy_flow,
        "sell_flow_cny": sell_flow,
    }


def _save_snapshot(snapshot: dict, is_final: bool = True) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with storage.get_connection() as conn:
        conn.execute(
            "DELETE FROM daily_position_snapshots WHERE snapshot_date = ?",
            (snapshot["date"],),
        )
        conn.executemany(
            """
            INSERT INTO daily_position_snapshots
                (snapshot_date, security_id, shares, average_cost, close_price,
                 cny_rate, market_value_cny, cost_value_cny, unrealized_pnl_cny)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot["date"],
                    row["security_id"],
                    str(row["shares"]),
                    str(row["average_cost"]),
                    str(row["close_price"]),
                    str(row["cny_rate"]),
                    str(row["market_value_cny"]),
                    str(row["cost_value_cny"]),
                    str(row["unrealized_pnl_cny"]),
                )
                for row in snapshot["details"]
            ],
        )
        conn.execute(
            """
            INSERT INTO daily_portfolio_snapshots
                (snapshot_date, total_market_value_cny, daily_pnl_cny,
                 cumulative_pnl_cny, realized_pnl_cny, unrealized_pnl_cny,
                 buy_flow_cny, sell_flow_cny, status, is_final,
                 error_message, calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ok', ?, NULL, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                total_market_value_cny = excluded.total_market_value_cny,
                daily_pnl_cny = excluded.daily_pnl_cny,
                cumulative_pnl_cny = excluded.cumulative_pnl_cny,
                realized_pnl_cny = excluded.realized_pnl_cny,
                unrealized_pnl_cny = excluded.unrealized_pnl_cny,
                buy_flow_cny = excluded.buy_flow_cny,
                sell_flow_cny = excluded.sell_flow_cny,
                status = excluded.status,
                is_final = excluded.is_final,
                error_message = NULL,
                calculated_at = excluded.calculated_at
            """,
            (
                snapshot["date"],
                str(snapshot["total_market_value_cny"]),
                (
                    str(snapshot["daily_pnl_cny"])
                    if snapshot["daily_pnl_cny"] is not None
                    else None
                ),
                str(snapshot["cumulative_pnl_cny"]),
                str(snapshot["realized_pnl_cny"]),
                str(snapshot["unrealized_pnl_cny"]),
                str(snapshot["buy_flow_cny"]),
                str(snapshot["sell_flow_cny"]),
                int(is_final),
                now,
            ),
        )
        conn.commit()


def _record_incomplete(day: date, message: str) -> None:
    previous = _previous_valid_snapshot(day)
    previous_value = previous["total_market_value_cny"] if previous else "0"
    previous_cumulative = previous["cumulative_pnl_cny"] if previous else "0"
    now = datetime.now().isoformat(timespec="seconds")
    with storage.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_portfolio_snapshots
                (snapshot_date, total_market_value_cny, daily_pnl_cny,
                 cumulative_pnl_cny, realized_pnl_cny, unrealized_pnl_cny,
                 buy_flow_cny, sell_flow_cny, status, is_final,
                 error_message, calculated_at)
            VALUES (?, ?, NULL, ?, '0', '0', '0', '0', 'incomplete', 0, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                status = 'incomplete', is_final = 0,
                error_message = excluded.error_message,
                calculated_at = excluded.calculated_at
            """,
            (
                day.isoformat(),
                previous_value,
                previous_cumulative,
                message,
                now,
            ),
        )
        conn.commit()


def backfill_snapshots(start_date: date, end_date: date) -> dict:
    market_data = _market_data()
    storage.ensure_database()
    securities = ledger.list_securities(active_only=True)
    currencies = {security["currency"] for security in securities}
    started = datetime.now().isoformat(timespec="seconds")
    with storage.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sync_runs(started_at, start_date, end_date, status)
            VALUES (?, ?, ?, 'running')
            """,
            (started, start_date.isoformat(), end_date.isoformat()),
        )
        run_id = cursor.lastrowid
        conn.commit()

    errors: list[str] = []
    completed = 0
    try:
        if securities and start_date <= end_date:
            market_data.ensure_price_history(securities, start_date, end_date)
            market_data.ensure_rate_history(currencies, start_date, end_date)
        for day in _days(start_date, end_date):
            if not _has_valuation_activity(day):
                continue
            try:
                snapshot = value_portfolio(day)
                _save_snapshot(snapshot, is_final=True)
                completed += 1
            except Exception as exc:
                message = str(exc)
                errors.append(f"{day.isoformat()}: {message}")
                _record_incomplete(day, message)
        status = "partial" if errors else "ok"
    except Exception as exc:
        errors.append(str(exc))
        status = "failed"

    with storage.get_connection() as conn:
        conn.execute(
            """
            UPDATE sync_runs
            SET finished_at = ?, status = ?, details = ?
            WHERE id = ?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                status,
                json.dumps({"completed": completed, "errors": errors}, ensure_ascii=False),
                run_id,
            ),
        )
        conn.commit()
    return {"status": status, "completed": completed, "errors": errors}


def rebuild_from(start_date: date | str) -> dict:
    start = (
        start_date if isinstance(start_date, date) else date.fromisoformat(start_date)
    )
    end = date.today() - timedelta(days=1)
    with storage.get_connection() as conn:
        conn.execute(
            "DELETE FROM daily_position_snapshots WHERE snapshot_date >= ?",
            (start.isoformat(),),
        )
        conn.execute(
            "DELETE FROM daily_portfolio_snapshots WHERE snapshot_date >= ?",
            (start.isoformat(),),
        )
        conn.commit()
    if start > end:
        return {"status": "ok", "completed": 0, "errors": []}
    return backfill_snapshots(start, end)


def auto_backfill() -> dict:
    global _backfill_checked_at
    now = time.monotonic()
    if now - _backfill_checked_at < BACKFILL_CACHE_TTL_SECONDS:
        return {"status": "ok", "completed": 0, "errors": [], "cached": True}
    storage.ensure_database()
    first = ledger.earliest_ledger_date()
    if not first:
        _backfill_checked_at = now
        return {"status": "ok", "completed": 0, "errors": []}
    baseline = storage.get_setting(
        "portfolio_baseline_date",
        storage.HISTORY_BASELINE_DATE,
    ) or storage.HISTORY_BASELINE_DATE
    first = min(first, baseline)
    end = date.today() - timedelta(days=1)
    with storage.get_connection() as conn:
        row = conn.execute(
            """
            SELECT MAX(snapshot_date) AS last_day
            FROM daily_portfolio_snapshots WHERE status = 'ok'
            """
        ).fetchone()
        first_ok = conn.execute(
            """
            SELECT MIN(snapshot_date) AS first_day
            FROM daily_portfolio_snapshots WHERE status = 'ok'
            """
        ).fetchone()
        incomplete = conn.execute(
            """
            SELECT MIN(snapshot_date) AS first_incomplete
            FROM daily_portfolio_snapshots
            WHERE status != 'ok' AND snapshot_date <= ?
            """,
            (end.isoformat(),),
        ).fetchone()
    if incomplete and incomplete["first_incomplete"]:
        start = date.fromisoformat(incomplete["first_incomplete"])
        if start <= end:
            _backfill_checked_at = now
            return rebuild_from(start)
    first_day = date.fromisoformat(first)
    if first_ok and first_ok["first_day"]:
        earliest_ok = date.fromisoformat(first_ok["first_day"])
        if first_day < earliest_ok:
            _backfill_checked_at = now
            return backfill_snapshots(first_day, earliest_ok - timedelta(days=1))
    start = (
        date.fromisoformat(row["last_day"]) + timedelta(days=1)
        if row and row["last_day"]
        else first_day
    )
    if start > end:
        _backfill_checked_at = now
        return {"status": "ok", "completed": 0, "errors": []}
    _backfill_checked_at = now
    return backfill_snapshots(start, end)


def current_valuation() -> dict:
    global _current_cache
    now = time.monotonic()
    if _current_cache and now - _current_cache[0] < CURRENT_CACHE_TTL_SECONDS:
        return _current_cache[1]
    securities = _securities_by_id()
    positions = ledger.calculate_positions(date.today())
    active = [
        securities[security_id]
        for security_id, position in positions.items()
        if position.shares > ZERO
    ]
    if active:
        quotes, rates = _market_data().get_live_prices(active)
    else:
        quotes = {}
        rates = {"CNY": Decimal("1"), "USD": Decimal("0"), "HKD": Decimal("0")}
    rows = []
    total_value = ZERO
    total_cost = ZERO
    missing = []
    previous = _previous_valid_snapshot(date.today())
    previous_values: dict[int, Decimal] = {}
    today_buy_by_security: dict[int, Decimal] = {}
    today_sell_by_security: dict[int, Decimal] = {}
    if previous is not None:
        with storage.get_connection() as conn:
            previous_rows = conn.execute(
                """
                SELECT security_id, market_value_cny
                FROM daily_position_snapshots
                WHERE snapshot_date = ?
                """,
                (previous["snapshot_date"],),
            ).fetchall()
            previous_values = {
                row["security_id"]: Decimal(row["market_value_cny"])
                for row in previous_rows
            }
    for security in active:
        position = positions[security["id"]]
        quote = quotes[security["id"]]
        price = quote["price"]
        if price is None:
            missing.append(security["name"])
            continue
        rate = rates[security["currency"]]
        value = position.shares * price * rate
        cost = position.shares * position.average_cost * rate
        rows.append(
            {
                **security,
                "shares": position.shares,
                "average_cost": position.average_cost,
                "latest_price": price,
                "change_pct": quote["change_pct"],
                "quote_status": quote["status"],
                "cny_rate": rate,
                "market_value_cny": value,
                "cost_value_cny": cost,
                "unrealized_pnl_cny": value - cost,
                "unrealized_pnl_pct": (
                    (value - cost) / cost * Decimal("100") if cost else None
                ),
                "today_pnl_cny": None,
                "today_pnl_pct": None,
                "position_pct": None,
            }
        )
        total_value += value
        total_cost += cost

    realized = ZERO
    for event in ledger.realized_events(date.today()):
        currency = event["currency"]
        rate = market_data.get_cached_rate(currency, event["trade_date"])
        if rate is None:
            rate = rates[currency]
        realized += event["realized_pnl_native"] * rate
    unrealized = sum((row["unrealized_pnl_cny"] for row in rows), ZERO)
    today_buy = ZERO
    today_sell = ZERO
    with storage.get_connection() as conn:
        today_trades = conn.execute(
            """
            SELECT t.security_id, t.side, t.shares, t.price, s.currency
            FROM trades t JOIN securities s ON s.id = t.security_id
            WHERE t.trade_date = ?
            """,
            (date.today().isoformat(),),
        ).fetchall()
    for trade in today_trades:
        amount = (
            Decimal(trade["shares"])
            * Decimal(trade["price"])
            * rates[trade["currency"]]
        )
        if trade["side"] == "BUY":
            today_buy += amount
            today_buy_by_security[trade["security_id"]] = (
                today_buy_by_security.get(trade["security_id"], ZERO) + amount
            )
        else:
            today_sell += amount
            today_sell_by_security[trade["security_id"]] = (
                today_sell_by_security.get(trade["security_id"], ZERO) + amount
            )
    today_pnl = (
        total_value
        - Decimal(previous["total_market_value_cny"])
        - today_buy
        + today_sell
        if previous is not None and not missing
        else None
    )
    for row in rows:
        if total_value:
            row["position_pct"] = row["market_value_cny"] / total_value * Decimal("100")
        previous_value = previous_values.get(row["id"])
        if previous_value is None or missing:
            continue
        security_id = row["id"]
        security_today_pnl = (
            row["market_value_cny"]
            - previous_value
            - today_buy_by_security.get(security_id, ZERO)
            + today_sell_by_security.get(security_id, ZERO)
        )
        row["today_pnl_cny"] = security_today_pnl
        row["today_pnl_pct"] = (
            security_today_pnl / previous_value * Decimal("100")
            if previous_value
            else None
        )
    result = {
        "rows": rows,
        "total_market_value_cny": total_value,
        "total_cost_cny": total_cost,
        "realized_pnl_cny": realized,
        "unrealized_pnl_cny": unrealized,
        "total_pnl_cny": realized + unrealized,
        "total_pnl_pct": (
            (realized + unrealized) / total_cost * Decimal("100")
            if total_cost
            else None
        ),
        "today_pnl_cny": today_pnl,
        "today_pnl_pct": (
            today_pnl / Decimal(previous["total_market_value_cny"]) * Decimal("100")
            if today_pnl is not None
            and previous is not None
            and Decimal(previous["total_market_value_cny"])
            else None
        ),
        "missing": missing,
        "rates": rates,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _current_cache = (now, result)
    return result


def get_daily_returns(start_date: date | None = None, end_date: date | None = None) -> list[dict]:
    storage.ensure_database()
    clauses = ["status = 'ok'"]
    params = []
    if start_date:
        clauses.append("snapshot_date >= ?")
        params.append(start_date.isoformat())
    if end_date:
        clauses.append("snapshot_date <= ?")
        params.append(end_date.isoformat())
    with storage.get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM daily_portfolio_snapshots
            WHERE {' AND '.join(clauses)}
            ORDER BY snapshot_date
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_industry_allocation(current_rows: list[dict]) -> list[dict]:
    grouped: dict[str, Decimal] = {}
    total = sum((row["market_value_cny"] for row in current_rows), ZERO)
    for row in current_rows:
        industry = row["industry"] or "其他"
        grouped[industry] = grouped.get(industry, ZERO) + row["market_value_cny"]
    return [
        {
            "industry": industry,
            "market_value_cny": value,
            "position_pct": value / total * Decimal("100") if total else ZERO,
        }
        for industry, value in sorted(
            grouped.items(), key=lambda item: item[1], reverse=True
        )
    ]


def get_snapshot_details(snapshot_date: date | str) -> list[dict]:
    target = (
        snapshot_date.isoformat()
        if isinstance(snapshot_date, date)
        else str(snapshot_date)
    )
    storage.ensure_database()
    with storage.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT dps.*, s.market, s.code, s.name, s.currency, s.industry
            FROM daily_position_snapshots dps
            JOIN securities s ON s.id = dps.security_id
            WHERE dps.snapshot_date = ?
            ORDER BY CAST(dps.market_value_cny AS REAL) DESC
            """,
            (target,),
        ).fetchall()
    return [dict(row) for row in rows]
