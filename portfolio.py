"""Compatibility helpers for code that previously imported ``portfolio``.

The v2 application uses ``storage``, ``ledger`` and ``valuation`` directly.
"""

from __future__ import annotations

from datetime import date

import ledger
import storage


PORTFOLIO_DB_FILE = storage.DB_FILE

_INDUSTRY_MAP = {
    "600519": "食品饮料",
    "600809": "食品饮料",
    "600887": "食品饮料",
    "000333": "家电制造",
    "000651": "家电制造",
    "601318": "金融保险",
    "600276": "医药生物",
    "300015": "医药生物",
    "300059": "金融科技",
    "600900": "电力能源",
    "601985": "电力能源",
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
    "515030": "新能源车",
    "515790": "新能源",
    "518850": "黄金",
    "513050": "中概互联",
    "512010": "医药生物",
    "00700": "互联网",
    "09988": "互联网",
    "09618": "互联网",
    "03690": "互联网",
    "09999": "互联网",
    "01810": "消费电子",
    "02318": "金融保险",
    "00941": "电信运营",
    "AAPL": "消费电子",
    "MSFT": "软件服务",
    "GOOGL": "互联网",
    "AMZN": "互联网",
    "TSLA": "新能源车",
    "NVDA": "半导体",
    "META": "互联网",
    "BILI": "互联网",
}


def detect_industry(code: str, name: str = "") -> str:
    code = code.strip().upper()
    if code in _INDUSTRY_MAP:
        return _INDUSTRY_MAP[code]
    keywords = {
        "ETF": "ETF",
        "银行": "金融保险",
        "保险": "金融保险",
        "证券": "金融保险",
        "医药": "医药生物",
        "科技": "科技",
        "新能源": "新能源",
        "芯片": "半导体",
    }
    for keyword, industry in keywords.items():
        if keyword in name:
            return industry
    return "其他"


def load_portfolio() -> dict:
    storage.ensure_database()
    securities = {item["id"]: item for item in ledger.list_securities()}
    positions = ledger.calculate_positions(date.today())
    holdings = []
    for security_id, position in positions.items():
        if position.shares <= 0:
            continue
        security = securities[security_id]
        holdings.append(
            {
                "market": security["market"],
                "name": security["name"],
                "code": security["code"],
                "cost_price": float(position.average_cost),
                "shares": float(position.shares),
                "currency": security["currency"],
                "industry": security["industry"],
            }
        )
    return {"holdings": holdings}


def ensure_industry_fields() -> dict:
    return load_portfolio()


def get_summary(results: list[dict]) -> dict:
    valid = [row for row in results if row.get("market_value_cny") is not None]
    total_cost = sum(row.get("cost_total_cny", 0) for row in valid)
    total_value = sum(row.get("market_value_cny", 0) for row in valid)
    total_pnl = total_value - total_cost
    return {
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / total_cost * 100, 2)
        if total_cost
        else 0,
        "update_time": date.today().isoformat(),
        "count": len(valid),
    }
