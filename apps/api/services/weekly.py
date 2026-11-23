"""Week-end portfolio review from the same final snapshots as the ledger."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import sqlite3
import logging
import threading
import time

import requests

from apps.api.adapters import fundamentals
from apps.api.core.config import settings
from apps.api.core.market_time import portfolio_closed_through
from apps.api.repositories import storage

D = Decimal
_sync_lock = threading.Lock()
_last_attempt = 0.0


def sync_week():
    """Refresh NAV history before booking installments across an offline gap."""
    from apps.api.adapters import market_data
    from apps.api.domain import ledger
    from apps.api.services import funds, valuation

    global _last_attempt
    if (
        settings.offline_mode
        or not settings.history_enabled
        or not _sync_lock.acquire(False)
    ):
        return
    try:
        if _last_attempt and time.monotonic() - _last_attempt < 600:
            return
        through = friday(date.today())
        if date.today().weekday() < 5:
            through -= timedelta(days=7)
        if through > portfolio_closed_through():
            return
        _last_attempt = time.monotonic()
        with storage.get_connection() as conn:
            latest = conn.execute(
                "SELECT max(snapshot_date) FROM daily_portfolio_snapshots WHERE status='ok' AND is_final=1"
            ).fetchone()[0]
        start = date.fromisoformat(latest or storage.HISTORY_BASELINE_DATE)
        assets = ledger.list_securities(active_only=True)
        if not assets:
            return
        if latest and latest >= through.isoformat():
            # A delayed NAV may arrive after Friday's snapshot has been saved.
            start = through - timedelta(days=4)
            with storage.get_connection() as conn:
                pending = {
                    r[0]
                    for r in conn.execute(
                        """
                    SELECT DISTINCT d.security_id FROM daily_position_snapshots d
                    JOIN securities s ON s.id=d.security_id
                    WHERE s.asset_type='MUTUAL_FUND' AND d.snapshot_date BETWEEN ? AND ?
                    AND NOT EXISTS (SELECT 1 FROM market_prices p WHERE p.security_id=d.security_id
                      AND p.price_date=d.snapshot_date)""",
                        (start.isoformat(), through.isoformat()),
                    )
                }
            for asset in assets:
                if asset["id"] in pending:
                    market_data.fetch_historical_prices(asset, start, through)
            with storage.get_connection() as conn:
                revised = any(
                    D(old) != D(new)
                    for old, new in conn.execute(
                        """
                    SELECT d.close_price,p.close_price FROM daily_position_snapshots d
                    JOIN market_prices p ON p.security_id=d.security_id AND p.price_date=d.snapshot_date
                    WHERE d.snapshot_date BETWEEN ? AND ?""",
                        (start.isoformat(), through.isoformat()),
                    )
                )
            sync = funds.sync_recurring_investments(refresh_navs=False)
            if not revised and not sync["earliest_date"]:
                return
            if sync["earliest_date"]:
                start = min(start, date.fromisoformat(sync["earliest_date"]))
            valuation.backfill_snapshots(start, date.fromisoformat(latest))
            valuation.invalidate_caches()
            return
        market_data.ensure_price_history(assets, start, through)
        market_data.ensure_rate_history({s["currency"] for s in assets}, start, through)
        sync = funds.sync_recurring_investments(refresh_navs=False)
        if sync["earliest_date"]:
            start = min(start, date.fromisoformat(sync["earliest_date"]))
        valuation.backfill_snapshots(start, through)
        valuation.invalidate_caches()
    except Exception:
        logging.getLogger(__name__).exception("Weekly snapshot refresh failed")
    finally:
        _sync_lock.release()


def friday(day):
    return day + timedelta(days=4 - day.weekday())


def archive():
    conn = sqlite3.connect(storage.DB_FILE.with_suffix(".research.db"), timeout=15)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS evidence (market, code, checked, body, PRIMARY KEY(market,code))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS editions (week, revision INTEGER, body, updated, PRIMARY KEY(week,revision))"
    )
    return conn


def evidence(stock):
    market, code = stock["market"], stock["code"]
    today = date.today().isoformat()
    with archive() as conn:
        old = conn.execute(
            "SELECT checked,body FROM evidence WHERE market=? AND code=?",
            (market, code),
        ).fetchone()
    rows = json.loads(old[1]) if old else []
    if not settings.offline_mode and (not old or old[0] != today):
        try:
            fresh = fundamentals.fetch_reports(market, code)
            if fresh:
                # Keep earlier observations when an issuer revises a period.
                keyed = {(r["period"], r["label"], r["available"]): r for r in rows}
                for r in fresh:
                    key = (r["period"], r["label"], r["available"])
                    previous = keyed.get(key)
                    if previous and previous.get("primary") and not r.get("primary"):
                        r["primary"] = previous["primary"]
                    keyed[key] = r
                rows = list(keyed.values())
                with archive() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO evidence VALUES(?,?,?,?)",
                        (market, code, today, json.dumps(rows)),
                    )
        except (requests.RequestException, ValueError, TypeError, KeyError):
            pass
    return rows


LENSES = {
    "互联网": "把收入拆成用户量、变现率和获客支出，核对增长是否伴随经营现金流改善。",
    "食品饮料": "对照销量、出厂价和渠道库存，核对经销商回款能否支持账面利润。",
    "医药生物": "区分新品放量、价格变化和一次性授权收入，跟踪研发投入或门诊利用率。",
    "金融保险": "核对新业务价值、保险服务利润与偿付能力，检查投资收益对净利的影响。",
    "家电制造": "拆分销量、均价和海外业务，核对库存与经营现金流是否同步改善。",
    "电力能源": "结合上网电量、电价与维护资本开支，评估可供分配的现金。",
    "物流运输": "核对件量、单票收入和单票成本，区分规模增长与价格竞争。",
    "工程机械": "核对订单、出口结构、应收账款与回款，识别周期反弹的持续性。",
}
ISSUER_LENSES = {
    (
        "US",
        "BILI",
    ): "对照日活、广告收入增速与毛利率，再检查内容成本和经营现金流。下期广告增长若伴随毛利率回落，重审变现效率。",
    (
        "HK",
        "00700",
    ): "拆开游戏与广告的增长，再从经营现金流扣除资本开支。若算力投入持续增长而自由现金流走弱，复核盈利的含金量。",
    (
        "HK",
        "03690",
    ): "对照订单量、单均利润和补贴支出。订单扩张若依赖补贴且核心业务利润继续下滑，复核竞争优势。",
    (
        "HK",
        "09618",
    ): "对照零售毛利、履约费用率和新业务亏损。重点核查降价后新增订单能否覆盖履约成本。",
}


def assess(stock, reports, cutoff):
    eligible = [
        r for r in reports if r["period"] <= cutoff and r["available"] <= cutoff
    ]
    r = max(eligible, key=lambda x: (x["period"], x["available"]), default=None)
    stock["report"] = r
    stock["cross_check"] = None
    if (
        (stock["market"], stock["code"]) == ("US", "BILI")
        and "2026-08-27" <= cutoff
        and (not r or r["period"] <= "2026-06-30")
    ):
        stock["cross_check"] = {
            "text": "公司二季报显示广告收入同比增长 28%，快于总营收的 8%；毛利率从 36.5% 升至 37.2%。广告变现和毛利率支持经营改善，持续性要看下一季。",
            "date": "2026-08-27",
            "url": "https://www.sec.gov/Archives/edgar/data/1723690/000119312526371261/d434015dex991.htm",
        }
    if (
        (stock["market"], stock["code"]) == ("HK", "09618")
        and "2026-08-13" <= cutoff
        and (not r or r["period"] <= "2026-06-30")
    ):
        stock["cross_check"] = {
            "text": "京东二季度归母净利从 62 亿元升至 71 亿元，但履约费用率从 6.2% 升至 7.1%。利润改善同时伴随履约成本压力，下次复查零售经营利润。",
            "date": "2026-08-13",
            "url": "https://ir.jd.com/static-files/dec50deb-c588-4849-98e5-34d22f6e73e1.pdf",
        }
    stock["follow"] = ISSUER_LENSES.get(
        (stock["market"], stock["code"]),
        LENSES.get(
            stock["industry"],
            "对照定价、销量、利润和经营现金流，复核增长是否转化为股东可用的现金。",
        ),
    )
    stock["valuation"] = "等待与周末股价口径匹配的估值证据。"
    stock["direction"] = "等待证据"
    stock["reason"] = "尚缺截至本周可验证的公司财报，先保留观察。"
    if not r:
        return
    if stock["market"] == "A" and r["bps"] and D(r["bps"]) > 0:
        pb = D(stock["price"]) / D(r["bps"])
        stock["valuation"] = (
            f"股价相当于每股净资产的 {pb:.2f} 倍。若长期 ROE 为 10%，静态盈利收益率约 {10 / pb:.1f}%（情景假设）。核查公司能否持续达到该回报。"
        )
    if (date.fromisoformat(cutoff) - date.fromisoformat(r["period"])).days > 270:
        stock["reason"] = "最近可核实报表距估值日已超过九个月，优先补齐新披露。"
        return
    if None in (r["sales"], r["earnings"], r["profit"]):
        return
    sales, growth, profit = map(D, (r["sales"], r["earnings"], r["profit"]))
    stock["reason"] = f"营收同比 {sales:+.1f}%，归母净利润同比 {growth:+.1f}%。"
    if profit <= 0 or (sales < 0 and growth < 0):
        stock["direction"] = "暂缓追加，复核持有理由"
        stock["reason"] += (
            "公司仍亏损或收入与净利同步收缩；下一期重点核查成本、竞争和现金消耗。"
        )
    elif sales > 0 and growth > 0:
        stock["direction"] = "维持观察，跟踪经营改善"
        stock["reason"] += (
            "收入和净利同向增长；进一步核对现金转化及估值后，再判断追加投入的吸引力。"
        )
    else:
        stock["direction"] = "持有观察"
        stock["reason"] += "经营指标方向不一致，先核对利润率和一次性损益。"
    if (
        stock["industry"] != "金融保险"
        and r["cash_ps"]
        and r["eps"]
        and D(r["eps"]) > 0
    ):
        cover = D(r["cash_ps"]) / D(r["eps"])
        stock["reason"] += f" 同期每股经营现金流相当于每股收益的 {cover:.2f} 倍。"
        if cover < 0:
            stock["direction"] = "优先复核回款"
    # Compare year-on-year growth for matching fiscal periods, so that seasonal
    # businesses are not judged on the change from a full year to a quarter.
    prior_period = str(int(r["period"][:4]) - 1) + r["period"][4:]
    comparable = [
        p
        for p in eligible
        if p["period"] == prior_period
        and p["label"].replace(prior_period[:4], "")
        == r["label"].replace(r["period"][:4], "")
        and p["sales"] is not None
    ]
    if comparable:
        prior = max(comparable, key=lambda p: p["available"])
        delta = sales - D(prior["sales"])
        stock["reason"] += (
            f" 相比上年同一报告期，营收同比增速变化 {delta:+.1f} 个百分点。"
        )


def positions(conn, day):
    return {
        row["security_id"]: dict(row)
        for row in conn.execute(
            """
        SELECT d.*,s.market,s.name,s.industry,s.asset_type,s.code,
          (SELECT max(price_date) FROM market_prices p WHERE p.security_id=s.id AND p.price_date<=d.snapshot_date) price_date
        FROM daily_position_snapshots d JOIN securities s ON s.id=d.security_id
        WHERE snapshot_date=? ORDER BY s.market,s.code""",
            (day,),
        )
    }


def attribution(conn, start, end, before, after):
    from apps.api.services import valuation

    values = {
        sid: D(after.get(sid, {}).get("market_value_cny", "0"))
        - D(before.get(sid, {}).get("market_value_cny", "0"))
        for sid in before.keys() | after.keys()
    }
    for t in conn.execute(
        """
        SELECT t.*,s.currency,(SELECT cny_rate FROM exchange_rates r WHERE r.currency=s.currency
          AND rate_date<=trade_date ORDER BY rate_date DESC LIMIT 1) fx
        FROM effective_trades t JOIN securities s ON t.security_id=s.id
        WHERE trade_date>? AND trade_date<=?""",
        (start, end),
    ):
        rate = "1" if t["currency"] == "CNY" else t["fx"]
        if rate is None:
            return {}
        sid = t["security_id"]
        amount = D(t["shares"]) * D(t["price"]) * D(rate)
        values[sid] = values.get(sid, D(0)) + (
            amount if t["side"] == "SELL" else -amount
        )
    external_flows = valuation._external_flows_by_security(
        conn, date.fromisoformat(end), date.fromisoformat(start)
    )
    for sid, amount in external_flows.items():
        values[sid] = values.get(sid, D(0)) - amount
    return values


def report(week=None, edition=None, *, prefer_cached=False):
    storage.ensure_database()
    today = date.today()
    latest_closed = (
        friday(today) if today.weekday() >= 5 else friday(today) - timedelta(days=7)
    )
    if latest_closed > portfolio_closed_through():
        latest_closed -= timedelta(days=7)
    with storage.get_connection() as conn:
        conn.execute("BEGIN")
        snapshots = list(
            conn.execute(
                "SELECT * FROM daily_portfolio_snapshots WHERE snapshot_date<=? ORDER BY snapshot_date",
                (latest_closed.isoformat(),),
            )
        )
        weeks = sorted(
            {
                friday(date.fromisoformat(s["snapshot_date"])).isoformat()
                for s in snapshots
            },
            reverse=True,
        )
        if not weeks:
            return {"weeks": [], "issue": "等待第一个已结束交易周的估值快照。"}
        key = week.isoformat() if week else weeks[0]
        if key not in weeks:
            raise ValueError("所选周无快照")
        if edition is not None:
            with archive() as db:
                versions = db.execute(
                    "SELECT revision,body,updated FROM editions WHERE week=? ORDER BY revision DESC",
                    (key,),
                ).fetchall()
            for rev, payload, stamp in versions:
                if rev == edition:
                    return {
                        **json.loads(payload),
                        "weeks": weeks,
                        "revision": rev,
                        "updated": stamp,
                        "versions": [v[0] for v in versions],
                    }
            raise ValueError("所选周报版本不存在")
        monday = (date.fromisoformat(key) - timedelta(days=4)).isoformat()
        rows = [s for s in snapshots if monday <= s["snapshot_date"] <= key]
        valid = [s for s in rows if s["status"] == "ok" and s["is_final"]]
        if not valid:
            return {"weeks": weeks, "issue": f"{key} 当周快照待补齐。"}
        last = valid[-1]
        if prefer_cached:
            with archive() as db:
                cached_versions = db.execute(
                    "SELECT revision,body,updated FROM editions WHERE week=? ORDER BY revision DESC",
                    (key,),
                ).fetchall()
            if cached_versions:
                revision, encoded, updated = cached_versions[0]
                cached = json.loads(encoded)
                if cached.get("snapshot_at") == last["calculated_at"]:
                    return {
                        **cached, "weeks": weeks, "revision": revision, "updated": updated,
                        "versions": [version[0] for version in cached_versions],
                        "lag": (f"最近已结束周为 {latest_closed}，当前展示有快照的最近一周。"
                                if key < latest_closed.isoformat() and week is None else None),
                    }
        end = last["snapshot_date"]
        total = D(last["total_market_value_cny"])
        after = positions(conn, end)
        previous = next(
            (
                s
                for s in reversed(snapshots)
                if s["snapshot_date"] < monday and s["status"] == "ok" and s["is_final"]
            ),
            None,
        )
        complete = (
            previous is not None
            and len(rows) == len(valid)
            and end == key
            and (
                date.fromisoformat(monday)
                - date.fromisoformat(previous["snapshot_date"])
            ).days
            <= 7
        )
        warnings = []
        if not complete:
            warnings.append("跨周基线或期末快照不足，仅展示截至估值日的持仓。")
        stale = [
            p["name"]
            for p in after.values()
            if not p["price_date"] or p["price_date"] < end
        ]
        if stale:
            warnings.append("使用前次行情或净值：" + "、".join(stale))
        for currency in sorted(
            {
                "HKD" if p["market"] == "HK" else "USD"
                for p in after.values()
                if p["market"] in {"HK", "US"}
            }
        ):
            rate_day = conn.execute(
                "SELECT max(rate_date) FROM exchange_rates WHERE currency=? AND rate_date<=?",
                (currency, end),
            ).fetchone()[0]
            if not rate_day or rate_day < end:
                warnings.append(
                    f"{currency}/CNY 汇率可核实至 {rate_day or '未知日期'}。"
                )
        if key < latest_closed.isoformat() and week is None:
            lag = f"最近已结束周为 {latest_closed}，当前展示有快照的最近一周。"
        else:
            lag = None
        opening = D(previous["total_market_value_cny"]) if complete else None
        flow = (
            sum(
                (
                    D(s["buy_flow_cny"])
                    - D(s["sell_flow_cny"])
                    + D(s["external_flow_cny"])
                    for s in rows
                ),
                D(0),
            )
            if complete
            else None
        )
        profit = total - opening - flow if complete else None
        contrib = []
        if complete:
            start = previous["snapshot_date"]
            changes = attribution(conn, start, end, positions(conn, start), after)
            if abs(sum(changes.values(), D(0)) - profit) <= D("0.01"):
                names = dict(conn.execute("SELECT id,name FROM securities"))
                contrib = [
                    {"name": names[k], "amount": v}
                    for k, v in sorted(changes.items(), key=lambda x: -abs(x[1]))[:5]
                ]
            else:
                warnings.append("标的贡献与组合合计未对齐，归因待复核。")
        groups = defaultdict(Decimal)
        stocks = []
        for p in after.values():
            value = D(p["market_value_cny"])
            groups["场外基金" if p["asset_type"] == "MUTUAL_FUND" else "场内证券"] += (
                value
            )
            if p["asset_type"] != "STOCK":
                continue
            reason = conn.execute(
                """SELECT trade_date,reason_category,note FROM effective_trades WHERE security_id=?
                AND trade_date<=? AND side='BUY' AND (reason_category!='' OR note!='')
                ORDER BY trade_date DESC,sequence DESC LIMIT 1""",
                (p["security_id"], end),
            ).fetchone()
            stocks.append(
                {k: p[k] for k in ("market", "code", "name", "industry")}
                | {
                    "price": p["close_price"],
                    "weight": value * 100 / total if total else D(0),
                    "pnl": D(p["unrealized_pnl_cny"]),
                    "return_pct": D(p["unrealized_pnl_cny"])
                    * 100
                    / D(p["cost_value_cny"])
                    if D(p["cost_value_cny"]) > 0
                    else None,
                    "thesis": " · ".join(filter(None, reason))
                    if reason
                    else "待补充买入理由",
                }
            )
    ranked = sorted(stocks, key=lambda p: p["pnl"], reverse=True)
    gain = [p for p in ranked if p["pnl"] > 0][:5]
    loss = [p for p in reversed(ranked) if p["pnl"] < 0][:5]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for stock, reports in zip(gain + loss, pool.map(evidence, gain + loss)):
            assess(stock, reports, end)
    largest = max(after.values(), key=lambda p: D(p["market_value_cny"]), default=None)
    if largest and total:
        weight = D(largest["market_value_cny"]) / total
        warnings.append(
            f"最大单项为{largest['name']}，占 {weight * 100:.2f}%。其他价格与汇率固定时，该项回撤 10% 将使组合市值下降约 {weight * 10:.2f}%。"
        )
    for index in ("纳斯达克100", "标普500"):
        linked = [
            p
            for p in after.values()
            if p["asset_type"] != "STOCK" and index in p["name"]
        ]
        if len(linked) > 1 and total:
            exposure = sum(D(p["market_value_cny"]) for p in linked) * 100 / total
            warnings.append(
                f"{index}相关基金有 {len(linked)} 只，合计占 {exposure:.2f}%。按基金名称归集，实际底层权重需对照基金披露。"
            )
    body = dict(
        priorities=[
            f"{p['name']}（占组合 {p['weight']:.2f}%）· {p['direction']}。{p['follow']}"
            for p in sorted(
                gain + loss,
                key=lambda p: (
                    p["direction"].startswith(("暂缓", "优先")),
                    p["weight"],
                ),
                reverse=True,
            )[:3]
        ],
        week=key,
        end=end,
        opening=opening,
        closing=total,
        flow=flow,
        profit=profit,
        gain=gain,
        loss=loss,
        contributions=contrib,
        groups=groups,
        warnings=warnings,
        snapshot_at=last["calculated_at"],
    )
    encoded = json.dumps(body, default=str, ensure_ascii=False, sort_keys=True)
    with archive() as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute(
            "SELECT revision,body,updated FROM editions WHERE week=? ORDER BY revision DESC LIMIT 1",
            (key,),
        ).fetchone()
        if old and old[1] == encoded:
            revision, _, updated = old
        else:
            revision = old[0] + 1 if old else 1
            updated = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO editions VALUES(?,?,?,?)",
                (key, revision, encoded, updated),
            )
    return {
        **json.loads(encoded),
        "weeks": weeks,
        "revision": revision,
        "versions": list(range(revision, 0, -1)),
        "updated": updated,
        "lag": lag,
    }
