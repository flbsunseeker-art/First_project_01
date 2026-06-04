"""Streamlit 股票持仓仪表盘"""

import streamlit as st
import pandas as pd
import plotly.express as px
from portfolio import load_portfolio, save_portfolio, add_holding, remove_holding, get_summary, ensure_industry_fields
from fetcher import fetch_all_prices
from report import generate_report

st.set_page_config(page_title="股票持仓追踪器", page_icon="📈", layout="wide")
st.title("📈 多市场股票持仓追踪器")
st.caption("A 股 / 港股 / 美股 — 统一以人民币查看盈亏")

# 初始化：补全行业字段
portfolio = ensure_industry_fields()

# ── 侧边栏 ──
with st.sidebar:
    st.header("➕ 添加持仓")
    with st.form("add_form", clear_on_submit=True):
        market = st.selectbox("市场", ["A", "HK", "US"],
                              format_func=lambda x: {"A": "A 股", "HK": "港股", "US": "美股"}[x])
        name = st.text_input("股票名称")
        code = st.text_input("股票代码", placeholder="如 600519 / 00700 / AAPL")
        cost_price = st.number_input("买入成本价", min_value=0.0, step=0.01, format="%.2f")
        shares = st.number_input("持有股数", min_value=0, step=100)
        if st.form_submit_button("添加", width="stretch"):
            if name and code and cost_price > 0 and shares > 0:
                add_holding(market, name, code, cost_price, shares)
                st.success(f"已添加 {name}")
                st.rerun()
            else:
                st.error("请填写完整信息")

    st.divider()
    st.header("🗑️ 删除持仓")
    if portfolio["holdings"]:
        options = [f"{h['name']} ({h['code']})" for h in portfolio["holdings"]]
        del_idx = st.selectbox("选择", range(len(options)), format_func=lambda i: options[i])
        if st.button("删除", width="stretch"):
            remove_holding(del_idx)
            st.success("已删除")
            st.rerun()

# ── 主区域 ──
if not portfolio["holdings"]:
    st.info("还没有持仓数据，请在左侧添加")
    st.stop()

with st.spinner("正在获取最新价格..."):
    results, rates = fetch_all_prices(portfolio["holdings"])
    summary = get_summary(results)

# ── 顶部汇总 ──
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("总成本 (CNY)", f"{summary['total_cost']:,.2f}")
with col2:
    st.metric("总市值 (CNY)", f"{summary['total_value']:,.2f}")
with col3:
    pnl = summary["total_pnl"]
    st.metric("总盈亏 (CNY)", f"{pnl:+,.2f}", f"{summary['total_pnl_pct']:+.2f}%")
with col4:
    st.metric("更新时间", summary["update_time"])

st.divider()

# ── 构建 DataFrame ──
df = pd.DataFrame(results)

# 保留原始索引，用于排序后回写
df["_orig_idx"] = df.index

# 排序：市场分组 + 盈亏金额排序
market_order = {"A": 0, "HK": 1, "US": 2}
df["_market_sort"] = df["market"].map(market_order)
df["_pnl_sort"] = df["pnl"].apply(lambda x: (0, -abs(x)) if (x or 0) >= 0 else (1, -abs(x or 0)))
df = df.sort_values(["_market_sort", "_pnl_sort"]).reset_index(drop=True)

# 仓位占比
total_value = summary["total_value"] or 1
df["position_pct"] = df["market_value_cny"].apply(
    lambda x: round(x / total_value * 100, 2) if x else 0
)

# ── 持仓明细（查看 + 编辑 + 排序合一）──
st.subheader("持仓明细（成本价、股数、行业可编辑）")

# 纯数值 DataFrame（排序基于数值，不是字符串）
df_table = pd.DataFrame({
    "市场": df["market"],
    "名称": df["name"],
    "代码": df["code"],
    "行业": df["industry"],
    "成本价": df["cost_price"].astype(float),
    "币种": df["currency"],
    "最新价": df["latest_price"].astype(float),
    "股数": df["shares"].astype(int),
    "仓位%": df["position_pct"].astype(float),
    "成本(CNY)": df["cost_total_cny"].astype(float),
    "市值(CNY)": df["market_value_cny"].astype(float),
    "盈亏(CNY)": df["pnl"].astype(float),
    "盈亏率%": df["pnl_pct"].astype(float),
    "今日涨跌%": df["change_pct"].astype(float),
})

# Styler：格式化 + 盈亏红涨绿跌（不影响底层数值排序）
def color_pnl(val):
    if pd.isna(val):
        return ""
    return "color: #e74c3c; font-weight: bold" if val >= 0 else "color: #27ae60; font-weight: bold"

styled = df_table.style \
    .format({
        "成本价": "{:,.2f}", "最新价": "{:,.2f}", "股数": "{:,}",
        "仓位%": "{:+.2f}%", "成本(CNY)": "{:,.2f}", "市值(CNY)": "{:,.2f}",
        "盈亏(CNY)": "{:+,.2f}", "盈亏率%": "{:+.2f}%", "今日涨跌%": "{:+.2f}%",
    }, na_rep="—") \
    .map(color_pnl, subset=["盈亏(CNY)", "盈亏率%", "今日涨跌%"])

st.dataframe(styled, width="stretch", hide_index=True,
             height=min(len(df_table) * 38 + 40, 800))

# ── 编辑持仓（修改后自动保存）──
st.subheader("编辑持仓")

df_edit = pd.DataFrame({
    "名称": df["name"],
    "代码": df["code"],
    "行业": df["industry"],
    "成本价": df["cost_price"].astype(float),
    "股数": df["shares"].astype(int),
})

edited = st.data_editor(
    df_edit,
    column_config={
        "成本价": st.column_config.NumberColumn("成本价", help="双击编辑", format="%.2f", step=0.01),
        "股数": st.column_config.NumberColumn("股数", help="双击编辑", step=100),
        "行业": st.column_config.TextColumn("行业", help="双击编辑"),
    },
    disabled=["名称", "代码"],
    width="stretch",
    hide_index=True,
)

# 检测编辑并保存（通过 _orig_idx 映射回原始位置）
changed = False
for display_idx in range(len(edited)):
    orig_idx = df.iloc[display_idx]["_orig_idx"]
    orig = portfolio["holdings"][orig_idx]
    new_cost = edited.iloc[display_idx]["成本价"]
    new_shares = edited.iloc[display_idx]["股数"]
    new_industry = edited.iloc[display_idx]["行业"]
    if float(new_cost) != float(orig["cost_price"]):
        portfolio["holdings"][orig_idx]["cost_price"] = float(new_cost)
        changed = True
    if int(new_shares) != int(orig["shares"]):
        portfolio["holdings"][orig_idx]["shares"] = int(new_shares)
        changed = True
    if str(new_industry) != str(orig.get("industry", "")):
        portfolio["holdings"][orig_idx]["industry"] = str(new_industry)
        changed = True

if changed:
    save_portfolio(portfolio)
    st.toast("已自动保存", icon="✅")
    st.rerun()

# ── 图表 ──
st.divider()
chart_tab1, chart_tab2, chart_tab3 = st.tabs(["📊 盈亏分布", "🥧 持仓分布", "🏭 行业分布"])

with chart_tab1:
    pnl_data = df[df["pnl"].notna()][["name", "pnl"]].copy()
    pnl_data["color"] = pnl_data["pnl"].apply(lambda x: "盈利" if x >= 0 else "亏损")
    if not pnl_data.empty:
        fig = px.bar(pnl_data, x="name", y="pnl", color="color",
                     color_discrete_map={"盈利": "#e74c3c", "亏损": "#27ae60"},
                     labels={"name": "股票", "pnl": "盈亏(CNY)", "color": ""},
                     title="各股票盈亏金额")
        fig.update_layout(xaxis_tickangle=-30, showlegend=True)
        st.plotly_chart(fig, width="stretch")

with chart_tab2:
    pie_data = df[df["market_value_cny"].notna()][["name", "market_value_cny"]].copy()
    if not pie_data.empty:
        fig = px.pie(pie_data, values="market_value_cny", names="name", hole=0.4,
                     title="持仓市值占比")
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, width="stretch")

with chart_tab3:
    ind_data = df[df["market_value_cny"].notna()][["industry", "market_value_cny"]].copy()
    if not ind_data.empty:
        ind_grouped = ind_data.groupby("industry", as_index=False).sum()
        fig = px.pie(ind_grouped, values="market_value_cny", names="industry", hole=0.4,
                     title="行业分布")
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, width="stretch")

# ── 底部 ──
st.divider()
col_a, col_b = st.columns(2)
with col_a:
    if st.button("📄 生成 HTML 报告", width="stretch"):
        filepath = generate_report()
        if filepath:
            st.success(f"报告已生成: {filepath}")
with col_b:
    st.caption(f"汇率: USD/CNY = {rates['USD_CNY']:.4f} | HKD/CNY = {rates['HKD_CNY']:.4f}")
