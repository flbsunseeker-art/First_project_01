"""Fetch and cache the two price indices independently of the private ledger."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import logging
import sqlite3
from threading import Lock
from zoneinfo import ZoneInfo

import requests

from apps.api.core.config import settings
from apps.api.repositories import storage

INDICES = {"csi300": "000300", "csi500": "000905"}
_lock = Lock()
_logger = logging.getLogger(__name__)
_checked: dict[tuple[str, str, str, str], datetime] = {}
_market_zone = ZoneInfo("Asia/Shanghai")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(storage.DB_FILE.with_suffix(".benchmarks.db"))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS index_closes (
            code TEXT NOT NULL, day TEXT NOT NULL, close TEXT NOT NULL,
            source TEXT NOT NULL, PRIMARY KEY(code, day)
        )
    """)
    return conn


def cached(start: str, end: str) -> dict[str, dict[str, Decimal]]:
    result: dict[str, dict[str, Decimal]] = {key: {} for key in INDICES}
    if not storage.DB_FILE.with_suffix(".benchmarks.db").exists():
        return result
    with closing(_connect()) as conn:
        for key, code in INDICES.items():
            result[key] = {
                day: Decimal(close)
                for day, close in conn.execute(
                    "SELECT day, close FROM index_closes WHERE code=? AND day BETWEEN ? AND ?",
                    (code, start, end),
                )
            }
    return result


def _download(code: str, start: str, end: str) -> tuple[list[tuple[str, Decimal]], str]:
    url = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
    try:
        response = requests.get(url, params={
            "indexCode": code, "startDate": start.replace("-", ""), "endDate": end.replace("-", ""),
        }, timeout=(3, 4))
        response.raise_for_status()
        payload = response.json()
        if str(payload["code"]) == "200":
            rows = [
                (datetime.strptime(item["tradeDate"], "%Y%m%d").date().isoformat(),
                 Decimal(str(item["close"])))
                for item in payload["data"] if item["indexCode"] == code
            ]
            if rows:
                return rows, "csindex"
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError, InvalidOperation):
        pass

    symbol = f"sh{code}"
    response = requests.get(
        "https://web.ifzq.gtimg.cn/appstock/app/kline/kline",
        params={"param": f"{symbol},day,{start},{end},640"},
        timeout=(3, 4),
    )
    response.raise_for_status()
    rows = response.json()["data"][symbol]["day"]
    return [
        (row[0], Decimal(row[2])) for row in rows
    ], "tencent"


def refresh(start: str, end: str) -> None:
    if not _lock.acquire(blocking=False):
        return
    try:
        _refresh(start, end)
    finally:
        _lock.release()


def _refresh(start: str, end: str) -> None:
    if settings.offline_mode:
        return
    now = datetime.now(_market_zone)
    # The chart uses finalized snapshots and closing prices. Leave today's
    # intraday index values out even if a provider exposes a daily bar early.
    if now.hour < 16:
        end = min(end, (now.date() - timedelta(days=1)).isoformat())
    if start > end:
        return
    for code in INDICES.values():
        key = str(storage.DB_FILE), code, start, end
        last_check = _checked.get(key)
        if last_check and (now - last_check).total_seconds() < 300:
            continue
        _checked[key] = now
        try:
            quotes, source = _download(code, start, end)
            if not quotes:
                continue
            with closing(_connect()) as conn, conn:
                conn.executemany(
                    """
                    INSERT INTO index_closes VALUES (?, ?, ?, ?)
                    ON CONFLICT(code, day) DO UPDATE SET close=excluded.close, source=excluded.source
                    """,
                    [
                        (code, day, str(close), source) for day, close in quotes
                        if start <= day <= end and close.is_finite() and close > 0
                    ],
                )
        except Exception as exc:
            _logger.warning("Could not refresh benchmark %s: %s", code, exc)


def get_comparison(report: dict) -> dict:
    from apps.api.services.performance import compare

    days = [day for day in report["days"] if day["status"] == "ok"]
    if not days:
        return compare(report, {})
    start = report["fund_coverage_from"] or days[0]["date"]
    end = days[-1]["date"]
    result = compare(report, cached(start, end))
    if not result["points"] or result["through"] != end:
        refresh(start, end)
        result = compare(report, cached(start, end))
    return result
