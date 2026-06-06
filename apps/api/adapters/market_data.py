"""Live and historical market data adapters with SQLite caching."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd

from apps.api.adapters.fetcher import fetch_stock_price, get_exchange_rates
from apps.api.core.config import settings
from apps.api.repositories import storage


class MarketDataError(RuntimeError):
    pass


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
    if security["market"] == "A":
        frame = ak.stock_zh_a_hist(
            symbol=security["code"],
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
    date_col = "日期" if "日期" in frame.columns else frame.columns[0]
    close_col = "收盘" if "收盘" in frame.columns else "收盘价"
    return [
        (_date_text(row[date_col]), Decimal(str(row[close_col])))
        for _, row in frame.iterrows()
        if pd.notna(row[close_col])
    ]


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


def fetch_historical_prices(security: dict, start: date, end: date) -> int:
    rows: list[tuple[str, Decimal]] = []
    source = "akshare"
    if security["market"] in {"A", "HK"}:
        try:
            rows = _akshare_history(security, start, end)
        except Exception:
            rows = []
    if not rows:
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
    acceptable_last_day = end - timedelta(days=7)
    for security in securities:
        with storage.get_connection() as conn:
            row = conn.execute(
                """
                SELECT MIN(price_date) AS first_day, MAX(price_date) AS last_day
                FROM market_prices WHERE security_id = ?
                """,
                (security["id"],),
            ).fetchone()
        first_day = date.fromisoformat(row["first_day"]) if row["first_day"] else None
        last_day = date.fromisoformat(row["last_day"]) if row["last_day"] else None
        if (
            first_day is None
            or first_day > start
            or last_day is None
            or last_day < acceptable_last_day
        ):
            fetch_historical_prices(security, fetch_start, end)


def get_cached_price(security_id: int, day: date | str) -> Decimal | None:
    target = day.isoformat() if isinstance(day, date) else str(day)
    storage.ensure_database()
    with storage.get_connection() as conn:
        row = conn.execute(
            """
            SELECT close_price FROM market_prices
            WHERE security_id = ? AND price_date <= ?
            ORDER BY price_date DESC LIMIT 1
            """,
            (security_id, target),
        ).fetchone()
    return Decimal(row["close_price"]) if row else None


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
    acceptable_last_day = end - timedelta(days=7)
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
            or last_day < acceptable_last_day
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


def get_live_prices(securities: list[dict]) -> tuple[dict[int, dict], dict[str, Decimal]]:
    offline = settings.offline_mode
    raw_rates = (
        {"USD_CNY": 7.25, "HKD_CNY": 0.93}
        if offline
        else get_exchange_rates()
    )
    rates = {
        "CNY": Decimal("1"),
        "USD": Decimal(str(raw_rates["USD_CNY"])),
        "HKD": Decimal(str(raw_rates["HKD_CNY"])),
    }
    quotes: dict[int, dict] = {}

    def fetch_one(security):
        if offline:
            return security, None
        return security, fetch_stock_price(security["market"], security["code"])

    fetched = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(securities)))) as pool:
        futures = [pool.submit(fetch_one, security) for security in securities]
        for future in as_completed(futures):
            fetched.append(future.result())

    for security, info in fetched:
        if info and info.get("price"):
            quotes[security["id"]] = {
                "price": Decimal(str(info["price"])),
                "change_pct": Decimal(str(info.get("change_pct") or 0)),
                "status": "live",
            }
        else:
            cached = get_cached_price(security["id"], date.today())
            if cached is not None:
                quotes[security["id"]] = {
                    "price": cached,
                    "change_pct": None,
                    "status": "cached",
                }
            else:
                quotes[security["id"]] = {
                    "price": None,
                    "change_pct": None,
                    "status": "missing",
                }
    return quotes, rates
