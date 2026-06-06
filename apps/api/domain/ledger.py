"""Securities, trades, and moving-average position calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from apps.api.repositories import storage


ZERO = Decimal("0")
CURRENCY_BY_MARKET = {"A": "CNY", "HK": "HKD", "US": "USD"}
INDUSTRY_BY_CODE = {
    "600519": "食品饮料",
    "000333": "家电制造",
    "601318": "金融保险",
    "600276": "医药生物",
    "300059": "金融科技",
    "515030": "新能源车",
    "515790": "新能源",
    "518850": "黄金",
    "513050": "中概互联",
    "512010": "医药生物",
    "00700": "互联网",
    "09988": "互联网",
    "09618": "互联网",
    "03690": "互联网",
    "01810": "消费电子",
    "02318": "金融保险",
    "AAPL": "消费电子",
    "MSFT": "软件服务",
    "GOOGL": "互联网",
    "AMZN": "互联网",
    "TSLA": "新能源车",
    "NVDA": "半导体",
    "META": "互联网",
}


class LedgerError(ValueError):
    pass


@dataclass
class Position:
    security_id: int
    shares: Decimal = ZERO
    average_cost: Decimal = ZERO
    realized_pnl_native: Decimal = ZERO


def decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise LedgerError(f"无效数字: {value}") from exc


def _iso_date(value: date | str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)).isoformat()


def guess_industry(code: str, name: str = "") -> str:
    code = code.strip().upper()
    if code in INDUSTRY_BY_CODE:
        return INDUSTRY_BY_CODE[code]
    for keyword, industry in {
        "ETF": "ETF",
        "银行": "金融保险",
        "保险": "金融保险",
        "证券": "金融保险",
        "医药": "医药生物",
        "科技": "科技",
        "新能源": "新能源",
        "芯片": "半导体",
    }.items():
        if keyword in name:
            return industry
    return "其他"


def _validate_baseline_date(day: str) -> None:
    baseline = storage.get_setting("portfolio_baseline_date")
    if baseline and day < baseline:
        raise LedgerError(f"成交日期不能早于历史基线 {baseline}")


def list_securities(active_only: bool = False) -> list[dict]:
    storage.ensure_database()
    sql = "SELECT * FROM securities"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY CASE market WHEN 'A' THEN 1 WHEN 'HK' THEN 2 ELSE 3 END, code"
    with storage.get_connection() as conn:
        return [dict(row) for row in conn.execute(sql).fetchall()]


def get_security(security_id: int) -> dict:
    storage.ensure_database()
    with storage.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM securities WHERE id = ?", (security_id,)
        ).fetchone()
    if not row:
        raise LedgerError("证券不存在")
    return dict(row)


def find_security(market: str, code: str) -> dict | None:
    storage.ensure_database()
    with storage.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM securities WHERE market = ? AND code = ?",
            (market.strip().upper(), code.strip().upper()),
        ).fetchone()
    return dict(row) if row else None


def create_security(
    market: str,
    code: str,
    name: str,
    industry: str = "其他",
) -> int:
    market = market.strip().upper()
    code = code.strip().upper()
    name = name.strip()
    if market not in CURRENCY_BY_MARKET or not code or not name:
        raise LedgerError("市场、代码和名称不能为空")
    detected_industry = industry.strip()
    if not detected_industry or detected_industry == "其他":
        detected_industry = guess_industry(code, name)
    now = datetime.now().isoformat(timespec="seconds")
    storage.ensure_database()
    with storage.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO securities
                (market, code, name, currency, industry, industry_manual,
                 active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                market,
                code,
                name,
                CURRENCY_BY_MARKET[market],
                detected_industry,
                int(bool(industry.strip() and industry.strip() != "其他")),
                now,
                now,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def update_security_industry(security_id: int, industry: str) -> None:
    industry = industry.strip() or "其他"
    now = datetime.now().isoformat(timespec="seconds")
    storage.ensure_database()
    with storage.get_connection() as conn:
        conn.execute(
            """
            UPDATE securities
            SET industry = ?, industry_manual = 1, updated_at = ?
            WHERE id = ?
            """,
            (industry, now, security_id),
        )
        conn.commit()


def list_opening_positions() -> list[dict]:
    storage.ensure_database()
    with storage.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT op.*, s.market, s.code, s.name, s.currency, s.industry
            FROM opening_positions op
            JOIN securities s ON s.id = op.security_id
            ORDER BY op.start_date, op.id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _next_sequence(conn, trade_date: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 AS seq FROM trades WHERE trade_date = ?",
        (trade_date,),
    ).fetchone()
    return int(row["seq"])


def _calculate_positions_conn(conn, as_of_date: str) -> dict[int, Position]:
    positions: dict[int, Position] = {}
    openings = conn.execute(
        """
        SELECT security_id, shares, average_cost
        FROM opening_positions WHERE start_date <= ?
        """,
        (as_of_date,),
    ).fetchall()
    for row in openings:
        positions[row["security_id"]] = Position(
            security_id=row["security_id"],
            shares=decimal(row["shares"]),
            average_cost=decimal(row["average_cost"]),
        )

    trades = conn.execute(
        """
        SELECT * FROM trades WHERE trade_date <= ?
        ORDER BY trade_date, sequence, id
        """,
        (as_of_date,),
    ).fetchall()
    for trade in trades:
        security_id = trade["security_id"]
        position = positions.setdefault(security_id, Position(security_id))
        shares = decimal(trade["shares"])
        price = decimal(trade["price"])
        if trade["side"] == "BUY":
            new_shares = position.shares + shares
            total_cost = position.shares * position.average_cost + shares * price
            position.shares = new_shares
            position.average_cost = total_cost / new_shares
        else:
            if shares > position.shares:
                raise LedgerError(
                    f"{trade['trade_date']} 卖出股数超过当时持仓"
                )
            position.realized_pnl_native += (
                price - position.average_cost
            ) * shares
            position.shares -= shares
            if position.shares == ZERO:
                position.average_cost = ZERO
    return positions


def calculate_positions(as_of_date: date | str | None = None) -> dict[int, Position]:
    storage.ensure_database()
    day = _iso_date(as_of_date or date.today())
    with storage.get_connection() as conn:
        return _calculate_positions_conn(conn, day)


def record_trade(
    security_id: int,
    trade_date: date | str,
    side: str,
    shares,
    price,
    reason_category: str = "",
    note: str = "",
) -> int:
    day = _iso_date(trade_date)
    _validate_baseline_date(day)
    side = side.strip().upper()
    qty = decimal(shares)
    trade_price = decimal(price)
    if side not in {"BUY", "SELL"}:
        raise LedgerError("交易方向必须为 BUY 或 SELL")
    if qty <= ZERO or trade_price <= ZERO:
        raise LedgerError("成交股数和价格必须大于 0")
    reason_category = reason_category.strip()
    note = note.strip()

    storage.ensure_database()
    now = datetime.now().isoformat(timespec="seconds")
    with storage.get_connection() as conn:
        try:
            sequence = _next_sequence(conn, day)
            cursor = conn.execute(
                """
                INSERT INTO trades
                    (security_id, trade_date, sequence, side, shares, price,
                     reason_category, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    security_id,
                    day,
                    sequence,
                    side,
                    str(qty),
                    str(trade_price),
                    reason_category,
                    note,
                    now,
                    now,
                ),
            )
            _calculate_positions_conn(conn, date.today().isoformat())
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return cursor.lastrowid


def update_trade(
    trade_id: int,
    trade_date: date | str,
    side: str,
    shares,
    price,
    reason_category: str = "",
    note: str = "",
) -> None:
    day = _iso_date(trade_date)
    _validate_baseline_date(day)
    side = side.strip().upper()
    qty = decimal(shares)
    trade_price = decimal(price)
    if side not in {"BUY", "SELL"} or qty <= ZERO or trade_price <= ZERO:
        raise LedgerError("交易信息无效")
    reason_category = reason_category.strip()
    note = note.strip()
    now = datetime.now().isoformat(timespec="seconds")
    storage.ensure_database()
    with storage.get_connection() as conn:
        try:
            exists = conn.execute(
                "SELECT 1 FROM trades WHERE id = ?", (trade_id,)
            ).fetchone()
            if not exists:
                raise LedgerError("交易不存在")
            sequence = _next_sequence(conn, day)
            conn.execute(
                """
                UPDATE trades
                SET trade_date = ?, sequence = ?, side = ?, shares = ?,
                    price = ?, reason_category = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    day,
                    sequence,
                    side,
                    str(qty),
                    str(trade_price),
                    reason_category,
                    note,
                    now,
                    trade_id,
                ),
            )
            _calculate_positions_conn(conn, date.today().isoformat())
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def delete_trade(trade_id: int) -> None:
    storage.ensure_database()
    with storage.get_connection() as conn:
        try:
            conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
            _calculate_positions_conn(conn, date.today().isoformat())
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def list_trades() -> list[dict]:
    storage.ensure_database()
    with storage.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT t.*, s.market, s.code, s.name, s.currency, s.industry
            FROM trades t JOIN securities s ON s.id = t.security_id
            ORDER BY t.trade_date DESC, t.sequence DESC, t.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def realized_events(as_of_date: date | str | None = None) -> list[dict]:
    """Return realized P&L events in the security's native currency."""
    storage.ensure_database()
    day = _iso_date(as_of_date or date.today())
    events: list[dict] = []
    with storage.get_connection() as conn:
        securities = {
            row["id"]: dict(row)
            for row in conn.execute("SELECT * FROM securities").fetchall()
        }
        positions: dict[int, Position] = {}
        for row in conn.execute(
            """
            SELECT security_id, shares, average_cost
            FROM opening_positions WHERE start_date <= ?
            """,
            (day,),
        ).fetchall():
            positions[row["security_id"]] = Position(
                row["security_id"],
                decimal(row["shares"]),
                decimal(row["average_cost"]),
            )
        trades = conn.execute(
            """
            SELECT * FROM trades WHERE trade_date <= ?
            ORDER BY trade_date, sequence, id
            """,
            (day,),
        ).fetchall()
        for trade in trades:
            position = positions.setdefault(
                trade["security_id"], Position(trade["security_id"])
            )
            qty = decimal(trade["shares"])
            price = decimal(trade["price"])
            if trade["side"] == "BUY":
                new_qty = position.shares + qty
                position.average_cost = (
                    position.shares * position.average_cost + qty * price
                ) / new_qty
                position.shares = new_qty
                continue
            pnl = (price - position.average_cost) * qty
            security = securities[trade["security_id"]]
            events.append(
                {
                    "trade_id": trade["id"],
                    "security_id": trade["security_id"],
                    "trade_date": trade["trade_date"],
                    "currency": security["currency"],
                    "realized_pnl_native": pnl,
                }
            )
            position.shares -= qty
            if position.shares == ZERO:
                position.average_cost = ZERO
    return events


def earliest_ledger_date() -> str | None:
    storage.ensure_database()
    with storage.get_connection() as conn:
        row = conn.execute(
            """
            SELECT MIN(day) AS first_day FROM (
                SELECT start_date AS day FROM opening_positions
                UNION ALL
                SELECT trade_date AS day FROM trades
            )
            """
        ).fetchone()
    return row["first_day"] if row else None
