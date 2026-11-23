"""Live and historical market data adapters with SQLite caching."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from decimal import Decimal
import threading
import time

import pandas as pd
import requests

from apps.api.adapters.fetcher import fetch_stock_price, get_exchange_rates
from apps.api.core.config import settings
from apps.api.core.market_time import us_closed_through
from apps.api.repositories import storage


class MarketDataError(RuntimeError):
    pass


FUND_NAV_REFRESH_TTL_SECONDS = 60
_fund_nav_refresh_at: dict[tuple[str, int], float] = {}
_fund_nav_refresh_lock = threading.Lock()


def _latest_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _date_text(value) -> str:
    if hasattr(value, "date"):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    return pd.Timestamp(value).date().isoformat()


def _upsert_prices(security_id: int, rows: list[tuple[str, Decimal]], source: str) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with storage.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO market_prices
                (security_id, price_date, close_price, source, status, fetched_at)
            VALUES (?, ?, ?, ?, 'ok', ?)
            ON CONFLICT(security_id, price_date) DO UPDATE SET
                close_price = excluded.close_price,
                source = excluded.source,
                status = excluded.status,
                fetched_at = excluded.fetched_at
            """,
            [
                (security_id, day, str(price), source, now)
                for day, price in rows
                if price > 0
            ],
        )
        conn.commit()
    return len(rows)


def _akshare_history(security: dict, start: date, end: date) -> list[tuple[str, Decimal]]:
    import akshare as ak

    start_text = start.strftime("%Y%m%d")
    end_text = end.strftime("%Y%m%d")
    code = security["code"]
    if security.get("asset_type") == "MUTUAL_FUND" or security["market"] == "FUND":
        frame = ak.fund_open_fund_info_em(
            symbol=code,
            indicator="单位净值走势",
            period="成立来",
        )
    elif security["market"] == "A" and code.startswith(("5", "159")):
        prefix = "sh" if code.startswith("5") else "sz"
        frame = ak.fund_etf_hist_sina(symbol=f"{prefix}{code}")
    elif security["market"] == "A":
        frame = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_text,
            end_date=end_text,
            adjust="",
        )
    elif security["market"] == "HK":
        frame = ak.stock_hk_hist(
            symbol=security["code"],
            period="daily",
            start_date=start_text,
            end_date=end_text,
            adjust="",
        )
    else:
        return []
    if frame is None or frame.empty:
        return []
    if "净值日期" in frame.columns:
        date_col = "净值日期"
        close_col = "单位净值"
    else:
        date_col = "日期" if "日期" in frame.columns else "date"
        close_col = "收盘" if "收盘" in frame.columns else "close"
    rows = []
    for _, row in frame.iterrows():
        day = _date_text(row[date_col])
        if start.isoformat() <= day <= end.isoformat() and pd.notna(row[close_col]):
            rows.append((day, Decimal(str(row[close_col]))))
    return rows


def _yfinance_symbol(security: dict) -> str:
    if security["market"] == "US":
        return security["code"]
    if security["market"] == "HK":
        return f"{int(security['code']):04d}.HK"
    suffix = ".SS" if security["code"].startswith(("5", "6", "9")) else ".SZ"
    return f"{security['code']}{suffix}"


def _yfinance_history(
    security: dict, start: date, end: date
) -> list[tuple[str, Decimal]]:
    import yfinance as yf

    if security["market"] == "US":
        end = min(end, us_closed_through())
    if end < start:
        return []
    frame = yf.download(
        _yfinance_symbol(security),
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if frame is None or frame.empty:
        return []
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return [
        (_date_text(index), Decimal(str(value)))
        for index, value in close.dropna().items()
    ]


def _fund_nav_history(
    code: str, start: date, end: date, *, timeout: float | tuple[float, float] = 12
) -> list[tuple[str, Decimal]]:
    rows = []
    page = 1
    while True:
        response = requests.get("https://api.fund.eastmoney.com/f10/lsjz",
            params={"fundCode":code, "startDate":start.isoformat(), "endDate":end.isoformat(),
                    "pageIndex":page, "pageSize":20},
            headers={"Referer":f"https://fundf10.eastmoney.com/jjjz_{code}.html"}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        records = (payload.get("Data") or {}).get("LSJZList") or []
        if not records:
            if len(rows) < int(payload.get("TotalCount") or 0):
                raise ValueError("净值历史分页不完整")
            break
        if rows and records[0]["FSRQ"] >= rows[-1][0]:
            raise ValueError("净值历史分页重叠")
        rows.extend((r["FSRQ"], Decimal(str(r["DWJZ"]))) for r in records)
        if len(rows) >= int(payload["TotalCount"]):
            break
        page += 1
    return rows


def fetch_historical_prices(security: dict, start: date, end: date) -> int:
    rows: list[tuple[str, Decimal]] = []
    source = "akshare"
    if security["market"] == "FUND":
        try:
            rows = _fund_nav_history(security["code"], start, end)
        except (requests.RequestException, ValueError, KeyError):
            rows = []
        if rows:
            return _upsert_prices(security["id"], rows, "eastmoney-fund-nav")
    if security["market"] in {"A", "HK", "FUND"}:
        try:
            rows = _akshare_history(security, start, end)
        except Exception:
            rows = []
    if not rows and security["market"] != "FUND":
        source = "yfinance"
        try:
            rows = _yfinance_history(security, start, end)
        except Exception as exc:
            raise MarketDataError(
                f"{security['name']} 历史行情获取失败: {exc}"
            ) from exc
    if not rows:
        raise MarketDataError(f"{security['name']} 没有可用历史行情")
    return _upsert_prices(security["id"], rows, source)


def ensure_price_history(securities: list[dict], start: date, end: date) -> None:
    storage.ensure_database()
    fetch_start = start - timedelta(days=10)
    expected_last_day = _latest_weekday(end)
    for security in securities:
        with storage.get_connection() as conn:
            row = conn.execute(
                """
                SELECT MIN(price_date) AS first_day, MAX(price_date) AS last_day
                FROM market_prices WHERE security_id = ? AND status = 'ok'
                """,
                (security["id"],),
            ).fetchone()
        first_day = date.fromisoformat(row["first_day"]) if row["first_day"] else None
        last_day = date.fromisoformat(row["last_day"]) if row["last_day"] else None
        fund_recent_enough = (
            security.get("asset_type") == "MUTUAL_FUND"
            and last_day is not None
            and last_day >= end - timedelta(days=7)
        )
        if not fund_recent_enough and (
            first_day is None
            or first_day > start
            or last_day is None
            or last_day < expected_last_day
        ):
            fetch_historical_prices(security, fetch_start, end)


def get_cached_price(security_id: int, day: date | str) -> Decimal | None:
    target = day.isoformat() if isinstance(day, date) else str(day)
    storage.ensure_database()
    with storage.get_connection() as conn:
        row = conn.execute(
            """
            SELECT close_price FROM market_prices
            WHERE security_id = ? AND price_date <= ? AND status = 'ok'
            ORDER BY price_date DESC LIMIT 1
            """,
            (security_id, target),
        ).fetchone()
    return Decimal(row["close_price"]) if row else None


def get_cached_price_record(security_id: int, day: date | str) -> dict | None:
    target = day.isoformat() if isinstance(day, date) else str(day)
    storage.ensure_database()
    with storage.get_connection() as conn:
        row = conn.execute(
            """
            SELECT price_date, close_price, source, status
            FROM market_prices
            WHERE security_id = ? AND price_date <= ? AND status IN ('ok', 'indicative')
            ORDER BY price_date DESC LIMIT 1
            """,
            (security_id, target),
        ).fetchone()
    return dict(row) if row else None


def _cached_change_pct(security_id: int, day: date | str) -> Decimal | None:
    target = day.isoformat() if isinstance(day, date) else str(day)
    with storage.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT close_price FROM market_prices
            WHERE security_id = ? AND price_date <= ?
            ORDER BY price_date DESC LIMIT 2
            """,
            (security_id, target),
        ).fetchall()
    if len(rows) < 2:
        return None
    latest = Decimal(rows[0]["close_price"])
    previous = Decimal(rows[1]["close_price"])
    return (latest - previous) / previous * Decimal("100") if previous else None


def _refresh_primary_nav(security: dict, start: date, end: date) -> None:
    try:
        rows = _fund_nav_history(security["code"], start, end, timeout=(3, 5))
    except (requests.Timeout, requests.ConnectionError):
        rows = _fund_nav_history(security["code"], start, end, timeout=(3, 5))
    if not rows:
        raise MarketDataError("没有返回可用净值")
    _upsert_prices(security["id"], rows, "eastmoney-fund-nav")


def refresh_fund_navs(
    securities: list[dict], force: bool = False, *, primary_only: bool = False
) -> list[str]:
    funds = [
        security
        for security in securities
        if security.get("asset_type") == "MUTUAL_FUND"
        or security["market"] == "FUND"
    ]
    if not funds or settings.offline_mode:
        return []
    with _fund_nav_refresh_lock:
        start = date.today() - timedelta(days=14)
        end = date.today()
        pending = []
        for security in funds:
            key = (str(storage.DB_FILE), security["id"])
            checked_at = _fund_nav_refresh_at.get(key)
            if not force and checked_at is not None and time.monotonic() - checked_at < FUND_NAV_REFRESH_TTL_SECONDS:
                continue
            with storage.get_connection() as conn:
                plan = conn.execute("""SELECT coalesce(max(e.nav_date),p.start_date)
                    FROM fund_investment_plans p LEFT JOIN fund_plan_executions e ON e.plan_id=p.id
                    WHERE p.security_id=? AND p.active=1 GROUP BY p.id""", (security["id"],)).fetchone()
            since = min(start, date.fromisoformat(plan[0])) if plan else start
            pending.append((security, key, since))

        def update(item):
            security, key, since = item
            try:
                if primary_only:
                    _refresh_primary_nav(security, since, end)
                else:
                    fetch_historical_prices(security, since, end)
            except Exception as exc:
                return key, f"{security['code']}: {exc}"
            return key, None

        if primary_only and pending:
            with ThreadPoolExecutor(max_workers=min(8, len(pending))) as pool:
                results = list(pool.map(update, pending))
        else:
            # AkShare's fund fallback embeds V8 and is not thread-safe on macOS.
            results = [update(item) for item in pending]
        for key, _ in results:
            _fund_nav_refresh_at[key] = time.monotonic()
        return [error for _, error in results if error]


def _upsert_rates(currency: str, rows: list[tuple[str, Decimal]], source: str) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with storage.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO exchange_rates
                (currency, rate_date, cny_rate, source, status, fetched_at)
            VALUES (?, ?, ?, ?, 'ok', ?)
            ON CONFLICT(currency, rate_date) DO UPDATE SET
                cny_rate = excluded.cny_rate,
                source = excluded.source,
                status = excluded.status,
                fetched_at = excluded.fetched_at
            """,
            [
                (currency, day, str(rate), source, now)
                for day, rate in rows
                if rate > 0
            ],
        )
        conn.commit()
    return len(rows)


def fetch_historical_rates(currency: str, start: date, end: date) -> int:
    if currency == "CNY":
        return 0
    import yfinance as yf

    ticker = "CNY=X" if currency == "USD" else "HKDCNY=X"
    try:
        frame = yf.download(
            ticker,
            start=(start - timedelta(days=10)).isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
    except Exception as exc:
        raise MarketDataError(f"{currency}/CNY 历史汇率获取失败: {exc}") from exc
    if frame is None or frame.empty:
        raise MarketDataError(f"{currency}/CNY 没有可用历史汇率")
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    rows = [
        (_date_text(index), Decimal(str(value)))
        for index, value in close.dropna().items()
    ]
    return _upsert_rates(currency, rows, "yfinance")


def ensure_rate_history(currencies: set[str], start: date, end: date) -> None:
    storage.ensure_database()
    expected_last_day = _latest_weekday(end)
    for currency in currencies - {"CNY"}:
        with storage.get_connection() as conn:
            row = conn.execute(
                """
                SELECT MIN(rate_date) AS first_day, MAX(rate_date) AS last_day
                FROM exchange_rates WHERE currency = ?
                """,
                (currency,),
            ).fetchone()
        first_day = date.fromisoformat(row["first_day"]) if row["first_day"] else None
        last_day = date.fromisoformat(row["last_day"]) if row["last_day"] else None
        if (
            first_day is None
            or first_day > start
            or last_day is None
            or last_day < expected_last_day
        ):
            fetch_historical_rates(currency, start, end)


def get_cached_rate(currency: str, day: date | str) -> Decimal | None:
    if currency == "CNY":
        return Decimal("1")
    target = day.isoformat() if isinstance(day, date) else str(day)
    storage.ensure_database()
    with storage.get_connection() as conn:
        row = conn.execute(
            """
            SELECT cny_rate FROM exchange_rates
            WHERE currency = ? AND rate_date <= ?
            ORDER BY rate_date DESC LIMIT 1
            """,
            (currency, target),
        ).fetchone()
    return Decimal(row["cny_rate"]) if row else None


def get_cached_marks(securities: list[dict], day: date) -> tuple[dict, dict]:
    target = day.isoformat()
    quotes, rates = {}, {"CNY": Decimal("1")}
    with storage.get_connection() as conn:
        for currency in {item["currency"] for item in securities} - {"CNY"}:
            row = conn.execute(
                """SELECT cny_rate FROM exchange_rates
                   WHERE currency=? AND rate_date<=? AND status='ok'
                   ORDER BY rate_date DESC LIMIT 1""",
                (currency, target),
            ).fetchone()
            if row:
                rates[currency] = Decimal(row[0])
        for security in securities:
            security_id = security["id"]
            row = conn.execute(
                """SELECT price_date, close_price, status FROM market_prices
                   WHERE security_id=? AND price_date<=? AND status IN ('ok','indicative')
                   ORDER BY price_date DESC LIMIT 1""",
                (security_id, target),
            ).fetchone()
            quotes[security_id] = {
                "price": Decimal(row["close_price"]) if row else None,
                "price_date": row["price_date"] if row else None,
                "status": (row["status"] if row["status"] == "indicative" else "cached")
                if row else "missing",
                "change_pct": None,
            }
    return quotes, rates


def get_live_prices(
    securities: list[dict], *, refresh_navs: bool = True, warnings: list[str] | None = None
) -> tuple[dict[int, dict], dict[str, Decimal]]:
    offline = settings.offline_mode
    day = date.today()
    required_currencies = {security["currency"] for security in securities}
    raw_rates = (
        {"_status": "offline"}
        if offline or not (required_currencies - {"CNY"})
        else get_exchange_rates()
    )
    rates = {"CNY": Decimal("1")}
    for currency, key in {"USD": "USD_CNY", "HKD": "HKD_CNY"}.items():
        if currency not in required_currencies:
            continue
        live_rate = raw_rates.get(key) if raw_rates.get("_status") == "live" else None
        rate = Decimal(str(live_rate)) if live_rate else get_cached_rate(currency, day)
        if rate is None:
            raise MarketDataError(f"缺少 {currency}/CNY 汇率")
        rates[currency] = rate
        if not live_rate and warnings is not None:
            warnings.append(f"{currency}/CNY 汇率沿用缓存")
    quotes: dict[int, dict] = {}
    if refresh_navs:
        refresh_fund_navs(securities)
    funds = [
        security
        for security in securities
        if security.get("asset_type") == "MUTUAL_FUND"
        or security["market"] == "FUND"
    ]
    stocks = [security for security in securities if security not in funds]

    for security in funds:
        cached = get_cached_price_record(security["id"], date.today())
        if cached is None:
            quotes[security["id"]] = {
                "price": None,
                "change_pct": None,
                "price_date": None,
                "status": "missing",
            }
            continue
        quotes[security["id"]] = {
            "price": Decimal(cached["close_price"]),
            "change_pct": _cached_change_pct(security["id"], date.today()),
            "price_date": cached["price_date"],
            "status": "nav",
        }

    def fetch_one(security):
        if offline:
            return security, None
        return security, fetch_stock_price(security["market"], security["code"])

    fetched = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(securities)))) as pool:
        futures = [pool.submit(fetch_one, security) for security in stocks]
        for future in as_completed(futures):
            fetched.append(future.result())

    for security, info in fetched:
        cached = get_cached_price_record(security["id"], day)
        quote_date = info.get("price_date") if info else None
        if (info and info.get("price") and quote_date and quote_date <= day.isoformat()
                and (cached is None or quote_date >= cached["price_date"])):
            quotes[security["id"]] = {
                "price": Decimal(str(info["price"])),
                "change_pct": Decimal(str(info.get("change_pct") or 0)),
                "price_date": quote_date,
                "status": "live",
            }
        else:
            if cached is not None:
                if warnings is not None:
                    warnings.append(f"{security['code']} 行情沿用缓存")
                quotes[security["id"]] = {
                    "price": Decimal(cached["close_price"]),
                    "change_pct": None,
                    "price_date": cached["price_date"],
                    "status": "indicative" if cached["status"] == "indicative" else "cached",
                }
            else:
                quotes[security["id"]] = {
                    "price": None,
                    "change_pct": None,
                    "price_date": None,
                    "status": "missing",
                }
    return quotes, rates
