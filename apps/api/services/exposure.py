"""Look-through classifications covering stocks, ETFs and mutual funds."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

D = Decimal
DOMESTIC = "A 股市场"
HONG_KONG = "港股市场"
US = "美股市场"
UNKNOWN = "其他／待核实"
MARKETS = {"A": DOMESTIC, "HK": HONG_KONG, "US": US}

BROAD = {
    "007721": "标普 500", "050025": "标普 500",
    "018043": "纳斯达克 100", "040046": "纳斯达克 100",
    "110003": "上证 50", "110020": "沪深 300",
}
FUND_THEMES = {
    "003547": "债券", "217022": "债券", "003984": "新能源",
    "005827": "主动混合", "519773": "数据产业",
    "006327": "中概互联", "164906": "中概互联",
    **BROAD,
}
DOMESTIC_FUNDS = {"003547", "217022", "110003", "110020", "519773", "003984"}
DOMESTIC_ETFS = {"512010", "515030", "515790", "518850"}
US_FUNDS = {"007721", "050025", "018043", "040046"}

CSI = "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/"
# The index splits estimate exposure. For 005827, the portfolio allocation keeps
# the disclosed HK weight and assigns the 12.95% residual to domestic exposure.
MARKET_SOURCES = {
    "H30533": (
        ((HONG_KONG, D(".89")), (US, D(".11"))),
        "2026-03-31", "中国互联网 50 指数权重",
        CSI + "H30533factsheet.pdf",
    ),
    "H11136": (
        ((HONG_KONG, D(".775")), (US, D(".225"))),
        "2026-09-30", "中国互联网指数权重",
        CSI + "H11136factsheet.pdf",
    ),
    "005827": (
        ((DOMESTIC, D(".5514") + D(".1295")), (HONG_KONG, D(".3191"))),
        "2026-09-30", "易方达蓝筹精选基金季报",
        "https://notice.10jqka.com.cn/api/pdf/c0c50fbdf0d8053a.pdf",
    ),
}
SOURCE_BY_SECURITY = {
    ("A", "513050"): "H30533",
    ("FUND", "006327"): "H30533",
    ("FUND", "164906"): "H11136",
    ("FUND", "005827"): "005827",
}


def _theme(row: dict) -> str:
    if row["asset_type"] == "MUTUAL_FUND":
        return FUND_THEMES.get(row["code"], "待分类")
    return row["industry"] or "待分类"


def _market(row: dict) -> tuple[tuple[str, Decimal], ...]:
    code, market = row["code"], row["market"]
    source = SOURCE_BY_SECURITY.get((market, code))
    if source:
        return MARKET_SOURCES[source][0]
    if row["asset_type"] == "STOCK":
        label = MARKETS.get(market, UNKNOWN)
    elif market == "FUND" and code in US_FUNDS:
        label = US
    elif (market == "A" and code in DOMESTIC_ETFS) or (market == "FUND" and code in DOMESTIC_FUNDS):
        label = DOMESTIC
    else:
        label = UNKNOWN
    return ((label, D(1)),)


def breakdown(rows: list[dict]) -> dict:
    themes: dict[str, Decimal] = defaultdict(Decimal)
    markets: dict[str, Decimal] = defaultdict(Decimal)
    unresolved = []
    used = {}
    total = D(0)
    for row in rows:
        value = row["market_value_cny"]
        total += value
        themes[_theme(row)] += value
        assigned = D(0)
        for label, weight in _market(row):
            if label == UNKNOWN:
                continue
            portion = value * weight
            assigned += portion
            markets[label] += portion
        source = SOURCE_BY_SECURITY.get((row["market"], row["code"]))
        unmatched = value - assigned
        if unmatched:
            markets[UNKNOWN] += unmatched
            unresolved.append({
                "market": row["market"], "code": row["code"], "name": row["name"],
                "market_value_cny": unmatched, "holding_pct": unmatched / value * 100,
                "reason": (
                    "披露中未列为三类市场投向的剩余资产"
                    if source else "暂无可靠的市场投向拆分"
                ),
            })
        if source and source not in used:
            _, as_of, label, url = MARKET_SOURCES[source]
            used[source] = {"label": label, "as_of": as_of, "url": url}

    def shares(items: list, key: str) -> list[dict]:
        return [
            {key: label, "market_value_cny": value, "position_pct": value / total * 100 if total else D(0)}
            for label, value in items
        ]

    return {
        "industry": shares(sorted(themes.items(), key=lambda item: (-item[1], item[0])), "industry"),
        "market": shares([(label, markets[label]) for label in (DOMESTIC, HONG_KONG, US, UNKNOWN)
                          if label in markets], "market"),
        "allocation_total_cny": total,
        "market_sources": list(used.values()),
        "unresolved_market": sorted(unresolved, key=lambda item: -item["market_value_cny"]),
    }
