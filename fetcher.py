"""股票价格和汇率获取模块

A股/港股数据通过腾讯/新浪接口获取，美股用 yfinance。
"""

import requests
import yfinance as yf
import re

# 通用请求头
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn",
}

_session = requests.Session()
_session.headers.update(_HEADERS)


def get_a_share_price(code: str) -> dict | None:
    """获取 A 股最新价格（通过新浪财经接口）"""
    prefix = "sh" if code.startswith(("6", "5")) else "sz"
    url = f"https://hq.sinajs.cn/list={prefix}{code}"
    try:
        resp = _session.get(url, timeout=10)
        resp.encoding = "gbk"
        text = resp.text
        # 格式: var hq_str_sh600519="贵州茅台,1800.00,...";
        match = re.search(r'"(.+)"', text)
        if not match:
            return None
        fields = match.group(1).split(",")
        if len(fields) < 32:
            return None
        name = fields[0]
        current_price = float(fields[3]) if fields[3] else None
        prev_close = float(fields[2]) if fields[2] else None
        # 盘前/已收盘：当前价为 0 时用昨收价
        if not current_price or current_price == 0:
            current_price = prev_close
        if not current_price:
            return None
        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
        return {
            "price": current_price,
            "change_pct": round(change_pct, 2),
            "name": name,
        }
    except Exception as e:
        print(f"获取 A 股 {code} 失败: {e}")
        return None


def get_hk_stock_price(code: str) -> dict | None:
    """获取港股最新价格（通过新浪财经接口）"""
    url = f"https://hq.sinajs.cn/list=hk{code}"
    try:
        resp = _session.get(url, timeout=10)
        resp.encoding = "gbk"
        text = resp.text
        match = re.search(r'"(.+)"', text)
        if not match:
            return None
        fields = match.group(1).split(",")
        if len(fields) < 10:
            return None
        # 港股格式: 名称,开盘价,昨收,最高,最低,最新价,...
        name = fields[1] if len(fields) > 1 else code
        current_price = float(fields[6]) if fields[6] else None
        prev_close = float(fields[3]) if fields[3] else None
        if not current_price or current_price == 0:
            current_price = prev_close
        if not current_price:
            return None
        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
        return {
            "price": current_price,
            "change_pct": round(change_pct, 2),
            "name": name,
        }
    except Exception as e:
        print(f"获取港股 {code} 失败: {e}")
        return None


def get_us_stock_price(code: str) -> dict | None:
    """获取美股最新价格（通过新浪财经接口）"""
    url = f"https://hq.sinajs.cn/list=gb_{code.lower()}"
    try:
        resp = _session.get(url, timeout=10)
        resp.encoding = "gbk"
        text = resp.text
        match = re.search(r'"(.+)"', text)
        if not match:
            return None
        fields = match.group(1).split(",")
        if len(fields) < 10:
            return None
        # 美股格式: 名称,昨收,开盘,最高,最低,最新价,...
        name = fields[0] if fields[0] else code
        current_price = float(fields[1]) if fields[1] else None
        prev_close = float(fields[26]) if len(fields) > 26 and fields[26] else None
        if not current_price or current_price == 0:
            current_price = prev_close
        if not current_price:
            return None
        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
        return {
            "price": current_price,
            "change_pct": round(change_pct, 2),
            "name": name,
        }
    except Exception as e:
        print(f"获取美股 {code} 失败: {e}")
        return None


def get_exchange_rates() -> dict:
    """获取实时汇率 (USD/CNY, HKD/CNY)"""
    rates = {"USD_CNY": 7.25, "HKD_CNY": 0.93}
    try:
        # 通过新浪财经获取汇率
        url = "https://hq.sinajs.cn/list=fx_susdcny,fx_shkdcny"
        resp = _session.get(url, timeout=10)
        resp.encoding = "gbk"
        for line in resp.text.strip().split("\n"):
            match = re.search(r'hq_str_(\w+)="(.+)"', line)
            if not match:
                continue
            key, val = match.group(1), match.group(2)
            fields = val.split(",")
            if len(fields) >= 2:
                price = float(fields[1]) if fields[1] else None
                if price and price > 0:
                    if "usdcny" in key:
                        rates["USD_CNY"] = price
                    elif "hkdcny" in key:
                        rates["HKD_CNY"] = price
    except Exception as e:
        print(f"获取汇率失败，使用默认值: {e}")
    return rates


def fetch_stock_price(market: str, code: str) -> dict | None:
    """根据市场类型获取股票价格"""
    code = code.strip()
    if market == "A":
        return get_a_share_price(code)
    elif market == "HK":
        return get_hk_stock_price(code)
    elif market == "US":
        return get_us_stock_price(code)
    return None


def fetch_all_prices(holdings: list[dict]) -> tuple[list[dict], dict]:
    """批量获取所有持仓的最新价格和汇率"""
    rates = get_exchange_rates()
    results = []

    for h in holdings:
        info = fetch_stock_price(h["market"], h["code"])
        if info:
            latest_price = info["price"]
            change_pct = info["change_pct"]

            # 外币价格换算成人民币
            if h["currency"] == "USD":
                latest_price_cny = latest_price * rates["USD_CNY"]
                cost_cny = h["cost_price"] * rates["USD_CNY"]
            elif h["currency"] == "HKD":
                latest_price_cny = latest_price * rates["HKD_CNY"]
                cost_cny = h["cost_price"] * rates["HKD_CNY"]
            else:
                latest_price_cny = latest_price
                cost_cny = h["cost_price"]

            pnl = (latest_price_cny - cost_cny) * h["shares"]
            cost_total = cost_cny * h["shares"]
            market_value = latest_price_cny * h["shares"]
            pnl_pct = (latest_price_cny - cost_cny) / cost_cny * 100 if cost_cny else 0

            results.append({
                **h,
                "latest_price": latest_price,
                "latest_price_cny": round(latest_price_cny, 2),
                "change_pct": round(change_pct, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "cost_total_cny": round(cost_total, 2),
                "market_value_cny": round(market_value, 2),
            })
        else:
            results.append({
                **h,
                "latest_price": None,
                "latest_price_cny": None,
                "change_pct": None,
                "pnl": None,
                "pnl_pct": None,
                "cost_total_cny": None,
                "market_value_cny": None,
            })

    return results, rates
