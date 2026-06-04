"""持仓管理模块"""

import json
import os
from datetime import datetime

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")

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


def load_portfolio() -> dict:
    """加载持仓数据"""
    if not os.path.exists(PORTFOLIO_FILE):
        return {"holdings": []}
    with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_portfolio(data: dict):
    """保存持仓数据"""
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_holding(market: str, name: str, code: str, cost_price: float, shares: int):
    """添加持仓"""
    data = load_portfolio()
    currency_map = {"A": "CNY", "HK": "HKD", "US": "USD"}
    data["holdings"].append({
        "market": market,
        "name": name,
        "code": code.strip(),
        "cost_price": cost_price,
        "shares": shares,
        "currency": currency_map.get(market, "CNY"),
        "industry": detect_industry(code, name),
    })
    save_portfolio(data)


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
    data = load_portfolio()
    if 0 <= index < len(data["holdings"]):
        data["holdings"].pop(index)
        save_portfolio(data)


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
