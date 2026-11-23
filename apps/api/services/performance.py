"""Portfolio performance derived from the same finalized snapshots as the ledger."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from apps.api.repositories import storage

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)


def history(as_of: date | None = None, *, calendar: bool = False) -> dict:
    storage.ensure_database()
    today = as_of or date.today()
    with storage.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT snapshot_date, total_market_value_cny, daily_pnl_cny, status, is_final
            FROM daily_portfolio_snapshots WHERE snapshot_date <= ?
            ORDER BY snapshot_date
            """,
            (today.isoformat(),),
        ).fetchall()
        first_fund = conn.execute(
            """
            SELECT MIN(p.snapshot_date)
            FROM daily_position_snapshots p
            JOIN daily_portfolio_snapshots d ON d.snapshot_date=p.snapshot_date
            JOIN securities s ON s.id=p.security_id
            WHERE s.asset_type='MUTUAL_FUND' AND d.status='ok' AND d.is_final=1
              AND p.snapshot_date <= ?
            """,
            (today.isoformat(),),
        ).fetchone()[0]

    previous: Decimal | None = None
    days = []
    for row in rows:
        complete = row["status"] == "ok" and bool(row["is_final"])
        total = Decimal(row["total_market_value_cny"]) if complete else None
        pnl = Decimal(row["daily_pnl_cny"]) if complete and row["daily_pnl_cny"] is not None else None
        rate = pnl / previous if pnl is not None and previous and previous > ZERO else None
        days.append({
            "date": row["snapshot_date"], "market_value": total, "pnl": pnl,
            "daily_rate": rate, "status": "ok" if complete else "incomplete",
        })
        if total is not None:
            previous = total

    result = {
        "as_of": today.isoformat(),
        "fund_coverage_from": first_fund,
        "days": days,
        "periods": _periods(days, today),
    }
    if calendar:
        result["calendar"] = calendar_buckets(days, today)
    return result


def _prior_year(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # February 29
        return day.replace(year=day.year - 1, day=28)


def _periods(days: Sequence[dict], today: date) -> dict:
    ranges = {
        "today": (today, today),
        "year": (date(today.year, 1, 1), today),
        "last_year": (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)),
        "rolling_year": (_prior_year(today) + timedelta(days=1), today),
    }
    return {key: summarize(days, begin, end) for key, (begin, end) in ranges.items()}


def summarize(days: Sequence[dict], begin: date, end: date) -> dict:
    start, finish = begin.isoformat(), end.isoformat()
    window = [day for day in days if start <= day["date"] <= finish]
    amounts = [day for day in window if day["pnl"] is not None]
    factor = ONE
    rates = [day["daily_rate"] for day in amounts]
    if rates and None not in rates:
        for rate in rates:
            factor *= ONE + rate
        percent = (factor - ONE) * HUNDRED
    else:
        percent = None
    first = amounts[0]["date"] if amounts else None
    last = amounts[-1]["date"] if amounts else None
    earliest_snapshot = next((day["date"] for day in days if day["status"] == "ok"), None)
    partial = bool(amounts) and (
        any(day["status"] != "ok" for day in window)
        or (earliest_snapshot is not None and earliest_snapshot > start)
        or (last is not None and (end - date.fromisoformat(last)).days > 4)
    )
    return {
        "pnl": sum((day["pnl"] for day in amounts), ZERO) if amounts else None,
        "return_pct": percent,
        "from_date": first,
        "through": last,
        "partial": partial,
    }


def calendar_buckets(days: Sequence[dict], today: date) -> dict:
    first_year = int(days[0]["date"][:4]) if days else today.year

    def bucket(start: date, end: date) -> dict:
        summary = summarize(days, start, min(end, today))
        return {
            "start": start.isoformat(), "end": end.isoformat(),
            **{key: summary[key] for key in ("pnl", "from_date", "through", "partial")},
        }

    months = {}
    weeks = {}
    years = []
    for year in range(first_year, today.year + 1):
        years.append(bucket(date(year, 1, 1), date(year, 12, 31)))
        for month in range(1, 13):
            start = date(year, month, 1)
            end = date(year, month, monthrange(year, month)[1])
            key = start.isoformat()[:7]
            months[key] = bucket(start, end)
            weeks[key] = []
            cursor = start
            while cursor <= end:
                next_end = min(cursor + timedelta(days=6 - cursor.weekday()), end)
                weeks[key].append(bucket(cursor, next_end))
                cursor = next_end + timedelta(days=1)
    return {"months": months, "weeks": weeks, "years": years}


def compare(report: dict, closes: dict[str, dict[str, Decimal]]) -> dict:
    days = report["days"]
    coverage = report["fund_coverage_from"]
    common = set.intersection(*(set(series) for series in closes.values())) if closes else set()
    comparable = [
        day["date"] for day in days
        if day["date"] in common and day["status"] == "ok"
        and (coverage is None or day["date"] >= coverage)
        and day["market_value"] is not None and day["market_value"] > ZERO
    ]
    def unavailable():
        return {"points": [], "from_date": None, "through": None, "excess": {}}

    if len(comparable) < 2:
        return unavailable()

    start = comparable[0]
    end = comparable[-1]
    baseline = {key: series[start] for key, series in closes.items()}
    factor = ONE
    points = []
    for day in days:
        when = day["date"]
        if when < start:
            continue
        if when > end:
            break
        if when != start and day["status"] == "ok":
            if day["daily_rate"] is None:
                break
            factor *= ONE + day["daily_rate"]
        if when in common and day["status"] == "ok":
            points.append({
                "date": when, "portfolio": (factor - ONE) * HUNDRED,
                **{
                    key: (series[when] / baseline[key] - ONE) * HUNDRED
                    for key, series in closes.items()
                },
            })
    if len(points) < 2:
        return unavailable()
    last = points[-1]
    return {
        "points": points, "from_date": start, "through": last["date"],
        "excess": {key: last["portfolio"] - last[key] for key in closes},
        "partial": any(start < day["date"] <= last["date"] and day["status"] != "ok" for day in days),
    }
