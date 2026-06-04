"""HTML 报告生成模块"""

import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from portfolio import load_portfolio, get_summary
from fetcher import fetch_all_prices


def generate_report(output_dir: str = None) -> str:
    """生成 HTML 报告，返回文件路径"""
    if output_dir is None:
        output_dir = os.path.dirname(__file__)

    portfolio = load_portfolio()
    if not portfolio["holdings"]:
        print("没有持仓数据，请先添加持仓")
        return ""

    results, rates = fetch_all_prices(portfolio["holdings"])
    summary = get_summary(results)

    # 添加仓位占比
    total_value = summary["total_value"]
    for r in results:
        if r.get("market_value_cny") and total_value:
            r["position_pct"] = round(r["market_value_cny"] / total_value * 100, 2)
        else:
            r["position_pct"] = 0

    # 按市场分组排序
    market_order = {"A": 0, "HK": 1, "US": 2}
    results.sort(key=lambda x: (market_order.get(x["market"], 9), -abs(x.get("pnl") or 0)))

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("report.html")

    html = template.render(
        holdings=results,
        summary=summary,
        rates=rates,
    )

    filename = f"report_{datetime.now().strftime('%Y-%m-%d')}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"报告已生成: {filepath}")
    print(f"总成本: {summary['total_cost']:,.2f} CNY")
    print(f"总市值: {summary['total_value']:,.2f} CNY")
    pnl_sign = "+" if summary["total_pnl"] >= 0 else ""
    print(f"总盈亏: {pnl_sign}{summary['total_pnl']:,.2f} CNY ({pnl_sign}{summary['total_pnl_pct']:.2f}%)")

    return filepath


if __name__ == "__main__":
    generate_report()
