"""Portfolio valuation, daily snapshots, and historical backfill."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from apps.api.core.market_time import portfolio_closed_through
from apps.api.domain import ledger
from apps.api.repositories import storage


ZERO = Decimal("0")
CURRENT_CACHE_TTL_SECONDS = 60
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


def _trade_flows(
    day: date, since: date | None = None
) -> tuple[Decimal, Decimal]:
    market_data = _market_data()
    buy = ZERO
    sell = ZERO
    with storage.get_connection() as conn:
        if since is None:
            rows = conn.execute(
                """
                SELECT t.side, t.shares, t.price, s.currency, t.trade_date
                FROM effective_trades t JOIN securities s ON s.id = t.security_id
                WHERE t.trade_date = ?
                """,
                (day.isoformat(),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT t.side, t.shares, t.price, s.currency, t.trade_date
                FROM effective_trades t JOIN securities s ON s.id = t.security_id
                WHERE t.trade_date > ? AND t.trade_date <= ?
                """,
                (since.isoformat(), day.isoformat()),
            ).fetchall()
    for row in rows:
        rate = market_data.get_cached_rate(row["currency"], row["trade_date"])
        if rate is None:
            raise market_data.MarketDataError(
                f"{row['trade_date']} 缺少 {row['currency']}/CNY 汇率"
            )
        amount = Decimal(row["shares"]) * Decimal(row["price"]) * rate
        if row["side"] == "BUY":
            buy += amount
        else:
            sell += amount
    return buy, sell


def _external_flows_by_security(
    conn, day: date, since: date | None = None, current_marks: dict | None = None
) -> dict[int, Decimal]:
    clauses = ["baseline_value_cny IS NOT NULL", "start_date <= ?"]
    params = [day.isoformat()]
    if since is not None:
        clauses.append("start_date > ?")
        params.append(since.isoformat())
    values = {
        sid: Decimal(amount)
        for sid, amount in conn.execute(
            f"SELECT security_id, baseline_value_cny FROM opening_positions "
            f"WHERE {' AND '.join(clauses)}",
            params,
        )
    }
    start = since.isoformat() if since is not None else ""
    end = day.isoformat()
    if not conn.execute(
        "SELECT 1 FROM position_reconciliations WHERE effective_date > ? AND effective_date <= ?",
        (start, end),
    ).fetchone():
        return values

    for sid, effective_date, currency, delta in ledger._replay_conn(conn, end)[2]:
        if effective_date <= start:
            continue
        mark = (current_marks or {}).get(sid) if effective_date == end else None
        if mark is None:
            quote = conn.execute(
                """SELECT close_price FROM market_prices
                   WHERE security_id = ? AND price_date <= ? AND status IN ('ok', 'indicative')
                   ORDER BY price_date DESC LIMIT 1""",
                (sid, effective_date),
            ).fetchone()
            price = Decimal(quote[0]) if quote else None
            rate = Decimal("1") if currency == "CNY" else None
            if rate is None:
                fx = conn.execute(
                    """SELECT cny_rate FROM exchange_rates WHERE currency = ? AND rate_date <= ?
                       ORDER BY rate_date DESC LIMIT 1""",
                    (currency, effective_date),
                ).fetchone()
                rate = Decimal(fx[0]) if fx else None
        else:
            price, rate = mark
        if price is None or rate is None:
            raise _market_data().MarketDataError(f"{effective_date} 缺少持仓校准行情或汇率 ({sid})")
        values[sid] = values.get(sid, ZERO) + delta * price * rate
    return values


def _external_flows(day: date, since: date | None = None) -> Decimal:
    with storage.get_connection() as conn:
        return sum(_external_flows_by_security(conn, day, since).values(), ZERO)


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
            """SELECT 1 FROM effective_trades WHERE trade_date = ?
               UNION ALL
               SELECT 1 FROM position_reconciliations WHERE effective_date = ?
               LIMIT 1""",
            (day.isoformat(), day.isoformat()),
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

    previous = _previous_valid_snapshot(valuation_date)
    previous_date = (
        date.fromisoformat(previous["snapshot_date"]) if previous is not None else None
    )
    realized = _realized_pnl_cny(valuation_date)
    buy_flow, sell_flow = _trade_flows(valuation_date, previous_date)
    external_flow = _external_flows(valuation_date, previous_date)
    if previous is None:
        daily_pnl = None
        cumulative = ZERO
    else:
        daily_pnl = (
            total_value
            - Decimal(previous["total_market_value_cny"])
            - buy_flow
            - external_flow
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
        "external_flow_cny": external_flow,
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
                 buy_flow_cny, sell_flow_cny, external_flow_cny, status, is_final,
                 error_message, calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok', ?, NULL, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                total_market_value_cny = excluded.total_market_value_cny,
                daily_pnl_cny = excluded.daily_pnl_cny,
                cumulative_pnl_cny = excluded.cumulative_pnl_cny,
                realized_pnl_cny = excluded.realized_pnl_cny,
                unrealized_pnl_cny = excluded.unrealized_pnl_cny,
                buy_flow_cny = excluded.buy_flow_cny,
                sell_flow_cny = excluded.sell_flow_cny,
                external_flow_cny = excluded.external_flow_cny,
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
                str(snapshot["external_flow_cny"]),
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


def backfill_snapshots(
    start_date: date, end_date: date, *, refresh_market_data: bool = True
) -> dict:
    end_date = min(end_date, portfolio_closed_through())
    if start_date > end_date:
        return {"status": "ok", "completed": 0, "errors": []}
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
        if refresh_market_data and securities and start_date <= end_date:
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
    end = portfolio_closed_through()
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


def auto_backfill(*, repair_history: bool = True) -> dict:
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
    end = portfolio_closed_through()
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
    if repair_history and incomplete and incomplete["first_incomplete"]:
        start = date.fromisoformat(incomplete["first_incomplete"])
        if start <= end:
            _backfill_checked_at = now
            return rebuild_from(start)
    first_day = date.fromisoformat(first)
    if repair_history and first_ok and first_ok["first_day"]:
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


def sync_installments() -> None:
    from apps.api.services import funds

    sync_result = funds.sync_recurring_investments()
    if sync_result["earliest_date"]:
        invalidate_caches()
        rebuild_from(sync_result["earliest_date"])


def latest_current_valuation() -> dict | None:
    cached = _current_cache
    return cached[1] if cached else None


def current_valuation(
    *, cached_only: bool = False, refresh_funds: bool = True, force_refresh: bool = False
) -> dict:
    global _current_cache
    now = time.monotonic()
    if (not cached_only and not force_refresh and _current_cache
            and now - _current_cache[0] < CURRENT_CACHE_TTL_SECONDS):
        return _current_cache[1]
    if not cached_only and refresh_funds:
        sync_installments()
    market_data = _market_data()
    day = date.today()
    securities = _securities_by_id()
    positions = ledger.calculate_positions(day)
    active = [
        securities[security_id]
        for security_id, position in positions.items()
        if position.shares > ZERO
    ]
    warnings: list[str] = []
    if cached_only:
        quotes, rates = market_data.get_cached_marks(active, day)
    elif active:
        quotes, rates = market_data.get_live_prices(
            active, refresh_navs=refresh_funds, warnings=warnings
        )
    else:
        quotes = {}
        rates = {"CNY": Decimal("1"), "USD": Decimal("0"), "HKD": Decimal("0")}
    rows = []
    total_value = ZERO
    total_cost = ZERO
    missing = []
    precise_today = day.weekday() < 5 and all(
        quotes[item["id"]]["price_date"] == day.isoformat()
        and quotes[item["id"]]["status"] != "indicative"
        for item in active
    )
    previous = _previous_valid_snapshot(day) if precise_today else None
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
        rate = rates.get(security["currency"])
        if price is None or rate is None:
            missing.append(security["name"])
            continue
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
                "price_date": quote.get("price_date"),
                "cny_rate": rate,
                "market_value_cny": value,
                "cost_value_cny": cost,
                "unrealized_pnl_cny": value - cost,
                "unrealized_pnl_pct": (
                    (value - cost) / cost * Decimal("100") if cost > ZERO else None
                ),
                "today_pnl_cny": None,
                "today_pnl_pct": None,
                "position_pct": None,
            }
        )
        total_value += value
        total_cost += cost

    realized = ZERO
    for event in ledger.realized_events(day):
        currency = event["currency"]
        rate = market_data.get_cached_rate(currency, event["trade_date"])
        if rate is None:
            rate = rates.get(currency)
        if rate is None:
            missing.append(f"{currency}/CNY 汇率")
            continue
        realized += event["realized_pnl_native"] * rate
    unrealized = sum((row["unrealized_pnl_cny"] for row in rows), ZERO)
    today_buy = ZERO
    today_sell = ZERO
    previous_date = (
        date.fromisoformat(previous["snapshot_date"]) if previous is not None else None
    )
    with storage.get_connection() as conn:
        if previous_date is None:
            today_trades = []
        else:
            today_trades = conn.execute(
                """
                SELECT t.security_id, t.side, t.shares, t.price, s.currency,
                       t.trade_date
                FROM effective_trades t JOIN securities s ON s.id = t.security_id
                WHERE t.trade_date > ? AND t.trade_date <= ?
                """,
                (previous_date.isoformat(), date.today().isoformat()),
            ).fetchall()
    for trade in today_trades:
        amount = (
            Decimal(trade["shares"])
            * Decimal(trade["price"])
            * (
                market_data.get_cached_rate(
                    trade["currency"], trade["trade_date"]
                )
                or rates[trade["currency"]]
            )
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
    external_by_security = {}
    if previous is not None and not missing:
        marks = {row["id"]: (row["latest_price"], row["cny_rate"]) for row in rows}
        with storage.get_connection() as conn:
            external_by_security = _external_flows_by_security(
                conn, date.today(), previous_date, marks
            )
    external_flow = sum(external_by_security.values(), ZERO)
    today_pnl = (
        total_value
        - Decimal(previous["total_market_value_cny"])
        - today_buy
        - external_flow
        + today_sell
        if previous is not None and not missing
        else None
    )
    for row in rows:
        if total_value and not missing:
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
            - external_by_security.get(security_id, ZERO)
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
        "warnings": warnings,
        "rates": rates,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    result["unvalued"] = [
        {
            **item, "shares": positions[item["id"]].shares,
            "average_cost": positions[item["id"]].average_cost,
            "latest_price": None, "cost_value_cny": None, "market_value_cny": None,
            "unrealized_pnl_cny": None, "quote_status": "missing",
        }
        for item in active if quotes[item["id"]]["price"] is None or item["currency"] not in rates
    ]
    if not cached_only:
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


def get_asset_value_trend(
    asset_group: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    if asset_group not in {"stocks", "funds"}:
        raise ValueError("asset_group must be stocks or funds")
    clauses = []
    params: list[str] = []
    if start_date:
        clauses.append("dps.snapshot_date >= ?")
        params.append(start_date.isoformat())
    if end_date:
        clauses.append("dps.snapshot_date <= ?")
        params.append(end_date.isoformat())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with storage.get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT dps.snapshot_date, dps.market_value_cny, s.asset_type
            FROM daily_position_snapshots dps
            JOIN securities s ON s.id = dps.security_id
            {where}
            ORDER BY dps.snapshot_date, dps.security_id
            """,
            params,
        ).fetchall()

    totals: dict[str, Decimal] = {}
    for row in rows:
        is_fund = row["asset_type"] == "MUTUAL_FUND"
        if (asset_group == "funds") != is_fund:
            continue
        day = row["snapshot_date"]
        totals[day] = totals.get(day, ZERO) + Decimal(row["market_value_cny"])
    return [
        {
            "snapshot_date": day,
            "total_market_value_cny": value,
            "cumulative_pnl_cny": ZERO,
            "daily_pnl_cny": None,
            "status": "ok",
        }
        for day, value in totals.items()
    ]


def get_industry_allocation(current_rows: list[dict]) -> list[dict]:
    current_rows = [
        row for row in current_rows if row.get("asset_type") != "MUTUAL_FUND"
    ]
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
            SELECT dps.*, s.market, s.code, s.name, s.currency, s.asset_type,
                   s.fund_category, s.industry
            FROM daily_position_snapshots dps
            JOIN securities s ON s.id = dps.security_id
            WHERE dps.snapshot_date = ?
            ORDER BY CAST(dps.market_value_cny AS REAL) DESC
            """,
            (target,),
        ).fetchall()
    return [dict(row) for row in rows]
