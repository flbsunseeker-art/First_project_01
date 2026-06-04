"""持仓管理模块"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PORTFOLIO_FILE = BASE_DIR / "portfolio.json"
PORTFOLIO_DB_FILE = Path(os.environ.get("PORTFOLIO_DB_FILE", BASE_DIR / "portfolio.db"))

# 常见股票行业映射（code -> industry）
_INDUSTRY_MAP = {
    # A 股
    "600519": "食品饮料", "600809": "食品饮料", "600887": "食品饮料",
    "000333": "家电制造", "000651": "家电制造",
    "601318": "金融保险",
    "600276": "医药生物", "300015": "医药生物",
    "300059": "金融科技",
    "600900": "电力能源", "601985": "电力能源",
    "600031": "工程机械",
    "002352": "物流运输",
    "600585": "水泥建材",
    "002415": "安防科技",
    "000568": "食品饮料",
    "601899": "有色金属",
    "002714": "农牧养殖",
    "000858": "食品饮料",
    "600309": "化工材料",
    "603259": "医药生物",
    "601012": "电力能源",
    # A 股 ETF
    "515030": "新能源车", "515790": "新能源", "518850": "黄金",
    "513050": "中概互联", "512010": "医药生物",
    # 港股
    "00700": "互联网", "09988": "互联网", "09618": "互联网",
    "03690": "互联网", "09999": "互联网", "01810": "消费电子",
    "02318": "金融保险", "00941": "电信运营",
    # 美股
    "AAPL": "消费电子", "MSFT": "软件服务", "GOOGL": "互联网",
    "AMZN": "互联网", "TSLA": "新能源车", "NVDA": "半导体",
    "META": "互联网", "BILI": "互联网",
}


def detect_industry(code: str, name: str = "") -> str:
    """根据代码和名称自动识别行业"""
    code = code.strip()
    if code in _INDUSTRY_MAP:
        return _INDUSTRY_MAP[code]
    # 关键词兜底
    keywords = {
        "ETF": "ETF", "银行": "金融保险", "保险": "金融保险",
        "证券": "金融保险", "地产": "房地产", "医药": "医药生物",
        "科技": "科技", "新能源": "新能源", "芯片": "半导体",
    }
    for kw, ind in keywords.items():
        if kw in name:
            return ind
    return "其他"


def _connect() -> sqlite3.Connection:
    """连接本地持仓数据库"""
    conn = sqlite3.connect(PORTFOLIO_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: sqlite3.Connection):
    """初始化数据库结构"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            name TEXT NOT NULL,
            code TEXT NOT NULL,
            cost_price REAL NOT NULL,
            shares INTEGER NOT NULL,
            currency TEXT NOT NULL,
            industry TEXT NOT NULL DEFAULT '其他',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()


def _get_metadata(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_metadata(conn: sqlite3.Connection, key: str, value: str):
    conn.execute(
        """
        INSERT INTO metadata (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _insert_holding(conn: sqlite3.Connection, holding: dict):
    now = datetime.now().isoformat(timespec="seconds")
    code = str(holding.get("code", "")).strip()
    name = str(holding.get("name", "")).strip()
    currency_map = {"A": "CNY", "HK": "HKD", "US": "USD"}
    market = str(holding.get("market", "A")).strip()
    conn.execute(
        """
        INSERT INTO holdings
            (market, name, code, cost_price, shares, currency, industry, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            market,
            name,
            code,
            float(holding.get("cost_price", 0)),
            int(holding.get("shares", 0)),
            str(holding.get("currency") or currency_map.get(market, "CNY")),
            str(holding.get("industry") or detect_industry(code, name)),
            now,
            now,
        ),
    )


def migrate_json_to_db() -> int:
    """把本地 portfolio.json 导入 SQLite，返回导入条数"""
    if not PORTFOLIO_FILE.exists():
        return 0

    with _connect() as conn:
        _init_db(conn)
        if _get_metadata(conn, "json_migrated") == "1":
            return 0

        with PORTFOLIO_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        holdings = data.get("holdings", [])
        existing_count = conn.execute("SELECT COUNT(*) AS count FROM holdings").fetchone()["count"]
        imported_count = 0
        if existing_count == 0:
            for holding in holdings:
                _insert_holding(conn, holding)
                imported_count += 1

        _set_metadata(conn, "json_migrated", "1")
        conn.commit()
        return imported_count


def ensure_storage_ready():
    """确保数据库存在，并在首次运行时从 JSON 迁移"""
    with _connect() as conn:
        _init_db(conn)
    migrate_json_to_db()


def load_portfolio() -> dict:
    """加载持仓数据"""
    ensure_storage_ready()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT market, name, code, cost_price, shares, currency, industry
            FROM holdings
            ORDER BY id
            """
        ).fetchall()
    return {"holdings": [dict(row) for row in rows]}


def save_portfolio(data: dict):
    """保存持仓数据"""
    ensure_storage_ready()
    with _connect() as conn:
        conn.execute("DELETE FROM holdings")
        for holding in data.get("holdings", []):
            _insert_holding(conn, holding)
        conn.commit()


def add_holding(market: str, name: str, code: str, cost_price: float, shares: int):
    """添加持仓"""
    currency_map = {"A": "CNY", "HK": "HKD", "US": "USD"}
    ensure_storage_ready()
    with _connect() as conn:
        _insert_holding(conn, {
            "market": market,
            "name": name,
            "code": code.strip(),
            "cost_price": cost_price,
            "shares": shares,
            "currency": currency_map.get(market, "CNY"),
            "industry": detect_industry(code, name),
        })
        conn.commit()


def ensure_industry_fields():
    """为现有持仓补全缺失的 industry 字段"""
    data = load_portfolio()
    changed = False
    for h in data["holdings"]:
        if "industry" not in h:
            h["industry"] = detect_industry(h["code"], h["name"])
            changed = True
    if changed:
        save_portfolio(data)
    return data


def remove_holding(index: int):
    """删除持仓"""
    ensure_storage_ready()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM holdings ORDER BY id LIMIT 1 OFFSET ?",
            (index,),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM holdings WHERE id = ?", (row["id"],))
            conn.commit()


def get_summary(results: list[dict]) -> dict:
    """计算汇总数据"""
    valid = [r for r in results if r["pnl"] is not None]
    total_cost = sum(r["cost_total_cny"] for r in valid)
    total_value = sum(r["market_value_cny"] for r in valid)
    total_pnl = sum(r["pnl"] for r in valid)
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

    return {
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(valid),
    }
