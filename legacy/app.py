"""Deprecated Streamlit prototype for the multi-market stock tracker.

The primary StockPilot app is now Next.js + FastAPI. This file remains as a
legacy reference while the migration finishes.
"""

from __future__ import annotations

import calendar
import io
from datetime import date
from decimal import Decimal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import ledger
import storage
import valuation
from report import generate_report


st.set_page_config(
    page_title="多市场股票收益追踪器",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.warning(
    "Streamlit 入口已标记为 legacy。StockPilot 主路径是 Next.js + FastAPI。",
    icon="⚠️",
)

st.markdown(
    """
    <style>
    .stApp { background: #07111f; color: #dbeafe; }
    [data-testid="stSidebar"] { background: #0b1728; }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #0f2239, #0b1728);
        border: 1px solid #1e3a5f;
        border-radius: 14px;
        padding: 14px;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.65rem;
        line-height: 1.2;
    }
    .calendar-grid {
        display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px;
        font-variant-numeric: tabular-nums;
    }
    .calendar-head { color: #7dd3fc; text-align: center; padding: 6px; }
    .calendar-day {
        min-height: 76px; padding: 8px; border-radius: 10px;
        background: #0f2239; border: 1px solid #1e3a5f;
    }
    .calendar-empty { min-height: 76px; }
    .calendar-date { color: #94a3b8; font-size: 12px; }
    .calendar-positive { color: #fb7185; font-weight: 700; margin-top: 10px; }
    .calendar-negative { color: #34d399; font-weight: 700; margin-top: 10px; }
    .calendar-neutral { color: #64748b; margin-top: 10px; }
    .data-note {
        background: #0f2239; border-left: 3px solid #38bdf8;
        padding: 10px 14px; border-radius: 8px; color: #bae6fd;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def initialize_app():
    migration = storage.ensure_database()
    sync = valuation.auto_backfill()
    return migration, sync


@st.cache_data(ttl=300, show_spinner=False)
def load_current_valuation():
    return valuation.current_valuation()


def clear_runtime_cache():
    load_current_valuation.clear()


def money(value) -> str:
    if value is None:
        return "—"
    return f"¥{float(value):,.2f}"


def signed_money(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):+,.2f}"


def profit_loss_color(value) -> str:
    if pd.isna(value):
        return ""
    color = "#ff4b4b" if float(value) >= 0 else "#00c781"
    return f"color: {color}; font-weight: 700"


def style_profit_loss(frame: pd.DataFrame, columns: list[str]):
    available = [column for column in columns if column in frame.columns]
    styled = frame.style
    if available:
        styled = styled.map(profit_loss_color, subset=available)
    return styled


def security_label(item: dict) -> str:
    return f"{item['name']} · {item['code']} · {item['market']}"


def render_calendar(rows: list[dict], year: int, month: int) -> None:
    pnl_by_day = {
        int(row["snapshot_date"][-2:]): (
            Decimal(row["daily_pnl_cny"])
            if row["daily_pnl_cny"] is not None
            else None
        )
        for row in rows
        if row["snapshot_date"].startswith(f"{year:04d}-{month:02d}")
    }
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    headers = "".join(
        f'<div class="calendar-head">{name}</div>'
        for name in ["一", "二", "三", "四", "五", "六", "日"]
    )
    cells = []
    for week in weeks:
        for day_number in week:
            if day_number == 0:
                cells.append('<div class="calendar-empty"></div>')
                continue
            pnl = pnl_by_day.get(day_number)
            if pnl is None:
                pnl_html = '<div class="calendar-neutral">—</div>'
            elif pnl >= 0:
                pnl_html = (
                    f'<div class="calendar-positive">+{float(pnl):,.2f}</div>'
                )
            else:
                pnl_html = (
                    f'<div class="calendar-negative">{float(pnl):,.2f}</div>'
                )
            cells.append(
                '<div class="calendar-day">'
                f'<div class="calendar-date">{day_number}</div>{pnl_html}</div>'
            )
    st.markdown(
        f'<div class="calendar-grid">{headers}{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )


def render_trade_form(securities: list[dict]) -> None:
    st.subheader("记录买卖")
    mode = st.radio(
        "证券",
        ["选择已有证券", "创建新证券"],
        horizontal=True,
        label_visibility="collapsed",
    )
    with st.form("record_trade", clear_on_submit=True):
        if mode == "选择已有证券":
            if not securities:
                st.info("请先创建证券")
                selected_id = None
            else:
                selected_id = st.selectbox(
                    "股票",
                    [item["id"] for item in securities],
                    format_func=lambda value: security_label(
                        next(item for item in securities if item["id"] == value)
                    ),
                )
        else:
            col1, col2 = st.columns(2)
            market = col1.selectbox("市场", ["A", "HK", "US"])
            code = col2.text_input("股票代码")
            name = col1.text_input("股票名称")
            industry = col2.text_input(
                "行业", placeholder="留空时自动识别，无法识别则归为其他"
            )
            selected_id = None

        col1, col2 = st.columns(2)
        side_text = col1.selectbox("方向", ["买入", "卖出"])
        trade_date = col2.date_input("成交日期", value=date.today())
        shares = col1.number_input(
            "成交股数", min_value=0.0, step=100.0, format="%.4f"
        )
        price = col2.number_input(
            "成交价格", min_value=0.0, step=0.01, format="%.4f"
        )
        submitted = st.form_submit_button("保存交易", width="stretch")

    if not submitted:
        return
    try:
        if mode == "创建新证券":
            selected_id = ledger.create_security(market, code, name, industry)
        if selected_id is None:
            raise ledger.LedgerError("请选择证券")
        ledger.record_trade(
            selected_id,
            trade_date,
            "BUY" if side_text == "买入" else "SELL",
            shares,
            price,
        )
        valuation.rebuild_from(trade_date)
        clear_runtime_cache()
        st.success("交易已保存，历史快照已重算")
        st.rerun()
    except Exception as exc:
        st.error(str(exc))


def render_trade_management(trades: list[dict]) -> None:
    if not trades:
        st.info("迁移后的期初持仓已保留。此后录入的买卖会显示在这里。")
        return
    frame = pd.DataFrame(
        [
            {
                "ID": row["id"],
                "日期": row["trade_date"],
                "方向": "买入" if row["side"] == "BUY" else "卖出",
                "市场": row["market"],
                "名称": row["name"],
                "代码": row["code"],
                "股数": float(row["shares"]),
                "成交价": float(row["price"]),
                "币种": row["currency"],
            }
            for row in trades
        ]
    )
    st.dataframe(frame, hide_index=True, width="stretch")
    trade_id = st.selectbox(
        "选择要修改或删除的交易",
        [row["id"] for row in trades],
        format_func=lambda value: next(
            f"{row['trade_date']} · {row['name']} · "
            f"{'买入' if row['side'] == 'BUY' else '卖出'} {row['shares']}"
            for row in trades
            if row["id"] == value
        ),
    )
    selected = next(row for row in trades if row["id"] == trade_id)
    with st.form("edit_trade"):
        col1, col2 = st.columns(2)
        edited_date = col1.date_input(
            "日期", value=date.fromisoformat(selected["trade_date"])
        )
        edited_side = col2.selectbox(
            "方向",
            ["BUY", "SELL"],
            index=0 if selected["side"] == "BUY" else 1,
            format_func=lambda value: "买入" if value == "BUY" else "卖出",
        )
        edited_shares = col1.number_input(
            "股数", value=float(selected["shares"]), min_value=0.0, format="%.4f"
        )
        edited_price = col2.number_input(
            "成交价", value=float(selected["price"]), min_value=0.0, format="%.4f"
        )
        save = st.form_submit_button("更新交易")
    if save:
        try:
            rebuild_day = min(
                date.fromisoformat(selected["trade_date"]), edited_date
            )
            ledger.update_trade(
                trade_id, edited_date, edited_side, edited_shares, edited_price
            )
            valuation.rebuild_from(rebuild_day)
            clear_runtime_cache()
            st.success("交易已更新")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if st.button("删除所选交易", type="secondary"):
        try:
            rebuild_day = date.fromisoformat(selected["trade_date"])
            ledger.delete_trade(trade_id)
            valuation.rebuild_from(rebuild_day)
            clear_runtime_cache()
            st.success("交易已删除")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def import_trades(upload) -> tuple[int, list[str]]:
    frame = pd.read_csv(upload)
    required = {
        "market",
        "code",
        "name",
        "side",
        "trade_date",
        "shares",
        "price",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"CSV 缺少字段: {', '.join(sorted(missing))}")
    securities = ledger.list_securities()
    by_key = {(item["market"], item["code"]): item["id"] for item in securities}
    imported = 0
    errors = []
    earliest = None
    for index, row in frame.iterrows():
        try:
            market = str(row["market"]).upper()
            code = str(row["code"]).strip().upper()
            security_id = by_key.get((market, code))
            if security_id is None:
                security_id = ledger.create_security(
                    market,
                    code,
                    str(row["name"]),
                    str(row.get("industry") or "其他"),
                )
                by_key[(market, code)] = security_id
            day = date.fromisoformat(str(row["trade_date"])[:10])
            ledger.record_trade(
                security_id,
                day,
                str(row["side"]).upper(),
                row["shares"],
                row["price"],
            )
            earliest = day if earliest is None else min(earliest, day)
            imported += 1
        except Exception as exc:
            errors.append(f"第 {index + 2} 行: {exc}")
    if earliest:
        valuation.rebuild_from(earliest)
    return imported, errors


migration_info, startup_sync = initialize_app()
securities = ledger.list_securities()
trades = ledger.list_trades()

st.title("多市场股票收益追踪器")
st.caption("A 股 · 港股 · 美股｜人民币统一估值｜手工交易流水")

with st.sidebar:
    render_trade_form(securities)
    st.divider()
    st.caption("第一版收益不包含现金、手续费和分红。")
    if migration_info.get("backup"):
        st.success("旧数据库已备份并完成迁移")

try:
    with st.spinner("正在获取最新行情..."):
        current = load_current_valuation()
except Exception as exc:
    st.error(f"当前估值失败：{exc}")
    current = {
        "rows": [],
        "total_market_value_cny": Decimal("0"),
        "total_cost_cny": Decimal("0"),
        "realized_pnl_cny": Decimal("0"),
        "unrealized_pnl_cny": Decimal("0"),
        "total_pnl_cny": Decimal("0"),
        "missing": [],
        "rates": {},
        "updated_at": "—",
    }

daily_rows = valuation.get_daily_returns()
latest_daily = next(
    (
        Decimal(row["daily_pnl_cny"])
        for row in reversed(daily_rows)
        if row["daily_pnl_cny"] is not None
    ),
    None,
)
today_pnl = current.get("today_pnl_cny")
total_cost = current["total_cost_cny"]
total_pnl = current["total_pnl_cny"]
total_pnl_pct = (
    total_pnl / total_cost * Decimal("100")
    if total_cost
    else Decimal("0")
)

summary_metrics = st.columns(4)
summary_metrics[0].metric("总投入成本 (CNY)", money(total_cost))
summary_metrics[1].metric(
    "股票总市值 (CNY)", money(current["total_market_value_cny"])
)
summary_metrics[2].metric(
    "累计盈亏 (CNY)",
    signed_money(total_pnl),
    delta=f"{float(total_pnl_pct):+.2f}%",
)
summary_metrics[3].metric("更新时间", current["updated_at"])

detail_metrics = st.columns(3)
detail_metrics[0].metric(
    "今日盈亏",
    signed_money(today_pnl if today_pnl is not None else latest_daily),
    help="当日尚无完整基准时显示最近交易日盈亏",
)
detail_metrics[1].metric(
    "已实现盈亏", signed_money(current["realized_pnl_cny"])
)
detail_metrics[2].metric(
    "未实现盈亏", signed_money(current["unrealized_pnl_cny"])
)

if current["missing"]:
    st.warning("缺少最新行情：" + "、".join(current["missing"]))
elif any(row["quote_status"] == "cached" for row in current["rows"]):
    st.info("部分证券正在使用最近有效收盘价。")
else:
    st.markdown(
        f'<div class="data-note">行情更新时间：{current["updated_at"]} · '
        f"历史补算状态：{startup_sync['status']}</div>",
        unsafe_allow_html=True,
    )

overview_tab, trade_tab, analysis_tab, data_tab = st.tabs(
    ["持仓总览", "交易流水", "收益分析", "数据管理"]
)

with overview_tab:
    if current["rows"]:
        total_value = current["total_market_value_cny"] or Decimal("1")
        holding_frame = pd.DataFrame(
            [
                {
                    "市场": row["market"],
                    "名称": row["name"],
                    "代码": row["code"],
                    "行业": row["industry"],
                    "成本价": float(row["average_cost"]),
                    "币种": row["currency"],
                    "最新价": float(row["latest_price"]),
                    "股数": float(row["shares"]),
                    "市值(CNY)": float(row["market_value_cny"]),
                    "成本(CNY)": float(row["cost_value_cny"]),
                    "盈亏(CNY)": float(row["unrealized_pnl_cny"]),
                    "盈亏率%": (
                        float(
                            row["unrealized_pnl_cny"]
                            / row["cost_value_cny"]
                            * Decimal("100")
                        )
                        if row["cost_value_cny"]
                        else 0
                    ),
                    "今日涨跌%": (
                        float(row["change_pct"])
                        if row["change_pct"] is not None
                        else None
                    ),
                    "仓位%": float(row["market_value_cny"] / total_value * 100),
                    "数据": row["quote_status"],
                }
                for row in current["rows"]
            ]
        )
        holding_styled = style_profit_loss(
            holding_frame,
            ["盈亏(CNY)", "盈亏率%", "今日涨跌%"],
        ).format(
                {
                    "股数": "{:,.4f}",
                    "成本价": "{:,.4f}",
                    "最新价": "{:,.4f}",
                    "市值(CNY)": "{:,.2f}",
                    "成本(CNY)": "{:,.2f}",
                    "盈亏(CNY)": "{:+,.2f}",
                    "盈亏率%": "{:+.2f}%",
                    "今日涨跌%": "{:+.2f}%",
                    "仓位%": "{:.2f}%",
                },
                na_rep="—",
            )
        st.dataframe(
            holding_styled,
            hide_index=True,
            width="stretch",
        )

        col1, col2 = st.columns(2)
        industry_rows = valuation.get_industry_allocation(current["rows"])
        industry_frame = pd.DataFrame(
            [
                {
                    "行业": row["industry"],
                    "市值": float(row["market_value_cny"]),
                    "占比": float(row["position_pct"]),
                }
                for row in industry_rows
            ]
        )
        col1.plotly_chart(
            px.pie(
                industry_frame,
                values="市值",
                names="行业",
                hole=0.55,
                title="行业分布",
            ),
            width="stretch",
        )
        market_frame = (
            holding_frame.groupby("市场", as_index=False)["市值(CNY)"].sum()
        )
        col2.plotly_chart(
            px.pie(
                market_frame,
                values="市值(CNY)",
                names="市场",
                hole=0.55,
                title="市场分布",
            ),
            width="stretch",
        )

        selected_industry = st.selectbox(
            "查看行业持仓", ["全部"] + industry_frame["行业"].tolist()
        )
        filtered = (
            holding_frame
            if selected_industry == "全部"
            else holding_frame[holding_frame["行业"] == selected_industry]
        )
        filtered_columns = [
            "名称",
            "代码",
            "行业",
            "市值(CNY)",
            "盈亏(CNY)",
            "盈亏率%",
            "仓位%",
        ]
        filtered_styled = style_profit_loss(
            filtered[filtered_columns],
            ["盈亏(CNY)", "盈亏率%"],
        ).format(
            {
                "市值(CNY)": "{:,.2f}",
                "盈亏(CNY)": "{:+,.2f}",
                "盈亏率%": "{:+.2f}%",
                "仓位%": "{:.2f}%",
            }
        )
        st.dataframe(
            filtered_styled,
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("还没有可估值的持仓，请在左侧录入第一笔买入。")

    st.subheader("编辑行业")
    security_frame = pd.DataFrame(
        [
            {
                "ID": item["id"],
                "市场": item["market"],
                "名称": item["name"],
                "代码": item["code"],
                "行业": item["industry"],
            }
            for item in securities
        ]
    )
    if not security_frame.empty:
        edited = st.data_editor(
            security_frame,
            disabled=["ID", "市场", "名称", "代码"],
            hide_index=True,
            width="stretch",
        )
        if st.button("保存行业修改"):
            original = security_frame.set_index("ID")
            for _, row in edited.iterrows():
                if str(row["行业"]) != str(original.loc[row["ID"], "行业"]):
                    ledger.update_security_industry(int(row["ID"]), str(row["行业"]))
            clear_runtime_cache()
            st.success("行业信息已保存")
            st.rerun()

with trade_tab:
    render_trade_management(trades)

with analysis_tab:
    if not daily_rows:
        st.info("历史起点建立后，系统会在后续交易日自动生成收益日历和曲线。")
    else:
        dates = [date.fromisoformat(row["snapshot_date"]) for row in daily_rows]
        month_options = sorted({(day.year, day.month) for day in dates}, reverse=True)
        selected_month = st.selectbox(
            "月份",
            month_options,
            format_func=lambda item: f"{item[0]} 年 {item[1]} 月",
        )
        render_calendar(daily_rows, *selected_month)

        detail_options = [
            row["snapshot_date"]
            for row in reversed(daily_rows)
            if row["daily_pnl_cny"] is not None
        ]
        if detail_options:
            selected_day = st.selectbox("查看日期明细", detail_options)
            selected_snapshot = next(
                row for row in daily_rows if row["snapshot_date"] == selected_day
            )
            st.json(
                {
                    "每日盈亏": signed_money(selected_snapshot["daily_pnl_cny"]),
                    "股票总市值": money(
                        selected_snapshot["total_market_value_cny"]
                    ),
                    "当日买入": money(selected_snapshot["buy_flow_cny"]),
                    "当日卖出": money(selected_snapshot["sell_flow_cny"]),
                    "累计收益": money(selected_snapshot["cumulative_pnl_cny"]),
                },
                expanded=True,
            )
            detail_rows = valuation.get_snapshot_details(selected_day)
            if detail_rows:
                detail_frame = pd.DataFrame(
                    [
                        {
                            "市场": row["market"],
                            "名称": row["name"],
                            "行业": row["industry"],
                            "股数": float(row["shares"]),
                            "收盘价": float(row["close_price"]),
                            "汇率": float(row["cny_rate"]),
                            "市值(CNY)": float(row["market_value_cny"]),
                            "未实现盈亏(CNY)": float(
                                row["unrealized_pnl_cny"]
                            ),
                            "未实现盈亏率%": (
                                float(
                                    Decimal(row["unrealized_pnl_cny"])
                                    / Decimal(row["cost_value_cny"])
                                    * Decimal("100")
                                )
                                if Decimal(row["cost_value_cny"])
                                else 0
                            ),
                        }
                        for row in detail_rows
                    ]
                )
                detail_styled = style_profit_loss(
                    detail_frame,
                    ["未实现盈亏(CNY)", "未实现盈亏率%"],
                ).format(
                    {
                        "股数": "{:,.4f}",
                        "收盘价": "{:,.4f}",
                        "汇率": "{:.4f}",
                        "市值(CNY)": "{:,.2f}",
                        "未实现盈亏(CNY)": "{:+,.2f}",
                        "未实现盈亏率%": "{:+.2f}%",
                    }
                )
                st.dataframe(
                    detail_styled,
                    hide_index=True,
                    width="stretch",
                )

        trend = pd.DataFrame(
            [
                {
                    "日期": pd.to_datetime(row["snapshot_date"]),
                    "股票总市值": float(row["total_market_value_cny"]),
                    "累计收益": float(row["cumulative_pnl_cny"]),
                    "每日盈亏": (
                        float(row["daily_pnl_cny"])
                        if row["daily_pnl_cny"] is not None
                        else 0
                    ),
                }
                for row in daily_rows
            ]
        )
        range_name = st.segmented_control(
            "时间范围",
            ["近 1 月", "今年", "近 1 年", "全部"],
            default="全部",
        )
        end_day = trend["日期"].max()
        if range_name == "近 1 月":
            trend = trend[trend["日期"] >= end_day - pd.Timedelta(days=31)]
        elif range_name == "今年":
            trend = trend[trend["日期"].dt.year == end_day.year]
        elif range_name == "近 1 年":
            trend = trend[trend["日期"] >= end_day - pd.Timedelta(days=365)]
        line_fig = go.Figure()
        line_fig.add_trace(
            go.Scatter(
                x=trend["日期"],
                y=trend["股票总市值"],
                name="股票总市值",
                line={"color": "#38bdf8", "width": 3},
            )
        )
        line_fig.add_trace(
            go.Scatter(
                x=trend["日期"],
                y=trend["累计收益"],
                name="累计收益",
                yaxis="y2",
                line={"color": "#f472b6", "width": 2},
            )
        )
        line_fig.update_layout(
            title="股票总市值与累计收益",
            yaxis={"title": "股票总市值（CNY）"},
            yaxis2={
                "title": "累计收益（CNY）",
                "overlaying": "y",
                "side": "right",
            },
            legend={"orientation": "h"},
        )
        st.plotly_chart(line_fig, width="stretch")
        colors = ["#fb7185" if value >= 0 else "#34d399" for value in trend["每日盈亏"]]
        st.plotly_chart(
            go.Figure(
                go.Bar(
                    x=trend["日期"],
                    y=trend["每日盈亏"],
                    marker_color=colors,
                    name="每日盈亏",
                )
            ).update_layout(title="每日盈亏"),
            width="stretch",
        )

with data_tab:
    st.subheader("同步状态")
    st.write(startup_sync)
    if st.button("重新补齐缺失历史"):
        result = valuation.auto_backfill()
        st.write(result)
        st.rerun()

    st.subheader("交易 CSV")
    export_frame = pd.DataFrame(
        [
            {
                "market": row["market"],
                "code": row["code"],
                "name": row["name"],
                "industry": row["industry"],
                "side": row["side"],
                "trade_date": row["trade_date"],
                "shares": row["shares"],
                "price": row["price"],
            }
            for row in trades
        ]
    )
    st.download_button(
        "导出交易 CSV",
        data=export_frame.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"trades-{date.today().isoformat()}.csv",
        mime="text/csv",
    )
    upload = st.file_uploader("导入交易 CSV", type=["csv"])
    if upload and st.button("确认导入"):
        try:
            imported, errors = import_trades(io.BytesIO(upload.getvalue()))
            clear_runtime_cache()
            st.success(f"成功导入 {imported} 笔交易")
            if errors:
                st.warning("\n".join(errors))
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.subheader("备份与报告")
    col1, col2 = st.columns(2)
    if col1.button("创建数据库备份"):
        path = storage.create_backup()
        col1.success(f"已备份至 {path}")
    if col2.button("生成 HTML 报告"):
        path = generate_report()
        col2.success(f"报告已生成：{path}")
