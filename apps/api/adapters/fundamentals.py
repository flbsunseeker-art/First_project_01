"""Dated financial evidence. Only public listing identifiers leave the device."""

from datetime import date
from decimal import Decimal, InvalidOperation
import re

import requests


TABLES = {
    "A": ("RPT_LICO_FN_CPD", "REPORTDATE"),
    "HK": ("RPT_HKF10_FN_MAININDICATOR", "STD_REPORT_DATE"),
    "US": ("RPT_USF10_FN_GMAININDICATOR", "STD_REPORT_DATE"),
}
# Some HK financial indicators omit the announcement date. Match the exact
# reporting period against issuer announcements before using them in a past week.
RELEASES = {
    ("HK", "00700", "2026-06-30"): (
        "2026-08-12",
        "https://www.tencent.com/investors/results/",
    ),
    ("HK", "00700", "2026-09-30"): (
        "2026-11-18",
        "https://www.tencent.com/wp-content/uploads/2026/11/E700_3Qresults.pdf",
    ),
    ("HK", "03690", "2026-06-30"): (
        "2026-08-28",
        "https://www.meituan.com/en-US/investor/results",
    ),
    ("HK", "09618", "2026-06-30"): (
        "2026-08-13",
        "https://ir.jd.com/static-files/dec50deb-c588-4849-98e5-34d22f6e73e1.pdf",
    ),
}


def number(value):
    try:
        n = Decimal(str(value))
        return str(n) if n.is_finite() else None
    except InvalidOperation:
        return None


def annual_disclosures(code):
    """Match the issuer's dated report, excluding summaries and board notices."""
    response = requests.get(
        "https://np-anotice-stock.eastmoney.com/api/security/ann",
        params={
            "stock_list": code,
            "page_size": 60,
            "page_index": 1,
            "ann_type": "A",
            "client_source": "web",
            "f_node": "1",
            "s_node": "0",
            "sr": "-1",
        },
        timeout=(8, 10),
    )
    response.raise_for_status()
    periods = {
        "第一季度": "03-31",
        "半年度": "06-30",
        "第三季度": "09-30",
        "年度": "12-31",
    }
    found = {}
    for item in (response.json().get("data") or {}).get("list") or []:
        if not any(c.get("stock_code") == code for c in item.get("codes", [])):
            continue
        match = re.search(
            r"(20\d{2})年?(第一季度|半年度|第三季度|年度)报告$", item.get("title") or ""
        )
        art = item.get("art_code") or ""
        if match and re.fullmatch(r"AN\d+", art):
            period = match[1] + "-" + periods[match[2]]
            found.setdefault(
                period,
                (
                    str(item["notice_date"])[:10],
                    f"https://data.eastmoney.com/notices/detail/{code}/{art}.html",
                ),
            )
    return found


def fetch_reports(market, code):
    if market not in TABLES or not re.fullmatch(r"[A-Z0-9.\-]{1,16}", code):
        return []
    table, period = TABLES[market]
    prefix = "" if market == "A" else "securities/"
    url = f"https://datacenter.eastmoney.com/{prefix}api/data/v1/get"
    params = {
        "reportName": table,
        "columns": "ALL",
        "pageSize": 60,
        "sortColumns": period,
        "sortTypes": "-1",
        "filter": f'(SECURITY_CODE="{code}")',
    }
    response = requests.get(url, params=params, timeout=(10, 12))
    response.raise_for_status()
    result = response.json(parse_float=Decimal).get("result") or {}
    disclosures = {}
    if market == "A":
        try:
            disclosures = annual_disclosures(code)
        except (requests.RequestException, ValueError, KeyError):
            pass
    reports = []
    for row in result.get("data") or []:
        if row.get("SECURITY_CODE") != code:
            continue
        end = str(row[period])[:10]
        released, primary = RELEASES.get((market, code, end), (None, None))
        declared = row.get("NOTICE_DATE") or released
        # A later update may contain a restatement. Use the conservative date.
        available = max(
            str(declared or date.today())[:10], str(row.get("UPDATE_DATE") or "")[:10]
        )
        if end in disclosures and disclosures[end][0] <= available:
            primary = disclosures[end][1]
        fields = (
            ("YSTZ", "SJLTZ", "PARENT_NETPROFIT", "MGJYXJJE", "BASIC_EPS", "BPS")
            if market == "A"
            else (
                "OPERATE_INCOME_YOY",
                "HOLDER_PROFIT_YOY"
                if market == "HK"
                else "PARENT_HOLDER_NETPROFIT_YOY",
                "HOLDER_PROFIT" if market == "HK" else "PARENT_HOLDER_NETPROFIT",
                "PER_NETCASH_OPERATE",
                "BASIC_EPS",
                "BPS",
            )
        )
        values = dict(
            zip(
                ("sales", "earnings", "profit", "cash_ps", "eps", "bps"),
                (number(row.get(key)) for key in fields),
            )
        )
        reports.append(
            {
                **values,
                "period": end,
                "published": str(declared)[:10] if declared else None,
                "available": available,
                "source": response.url,
                "primary": primary,
                "label": row.get("DATATYPE") or row.get("REPORT_TYPE") or end,
            }
        )
    return reports
