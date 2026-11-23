"""Build and archive a weekly diagnosis from a dated ledger snapshot."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field

from apps.api.core.market_time import SHANGHAI
from apps.api.repositories import storage
from apps.api.services import exposure, weekly


class Evidence(BaseModel):
    title: str
    url: AnyHttpUrl
    published_on: date
    note: str = ""
    assets: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    scope: Literal["组合", "个股"]
    title: str
    fact: str
    interpretation: str
    holding_view: str = ""
    selection_reason: str = ""
    previous_review: str = ""
    assets: list[str]
    evidence: list[str] = Field(default_factory=list)


class Strategy(BaseModel):
    finding: str
    direction: Literal["维持", "带条件观察", "优先复核配置"]
    action_label: str = ""
    action: str
    checkpoint: str


class Opportunity(BaseModel):
    title: str
    reasoning: str
    check: str
    evidence: list[str] = Field(min_length=1)


class DeferredCandidate(BaseModel):
    title: str
    reason: str
    assets: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(min_length=1)


class Analysis(BaseModel):
    summary: str
    strategy_summary: str
    outside_summary: str
    key_changes: list[str] = Field(default_factory=list, max_length=3)
    findings: list[Finding] = Field(max_length=6)
    strategies: list[Strategy]
    outside: list[Opportunity] = Field(max_length=2)
    deferred: list[DeferredCandidate] = Field(default_factory=list)
    evidence: dict[str, Evidence]


def _stock_ranks(assets: list[dict], stock_keys: set[str]) -> dict[str, list[str]]:
    ranked = sorted(
        (asset for asset in assets if asset["key"] in stock_keys),
        key=lambda asset: Decimal(asset["floating_pnl_cny"]),
        reverse=True,
    )
    return {
        "gains": [asset["key"] for asset in ranked if Decimal(asset["floating_pnl_cny"]) > 0][:5],
        "losses": [
            asset["key"] for asset in reversed(ranked) if Decimal(asset["floating_pnl_cny"]) < 0
        ][:5],
    }


def scan_week(cutoff_day: date) -> dict:
    if cutoff_day.weekday() != 6:
        raise ValueError("周报截止日期须为北京时间周日")
    period_start = cutoff_day - timedelta(days=6)
    cutoff = datetime.combine(cutoff_day, datetime.min.time(), SHANGHAI)
    expected_close = cutoff_day - timedelta(days=2)
    storage.ensure_database()
    with storage.get_connection() as conn:
        conn.execute("BEGIN")
        snapshots = conn.execute(
            """SELECT * FROM daily_portfolio_snapshots
               WHERE snapshot_date >= ? AND snapshot_date < ? ORDER BY snapshot_date""",
            (period_start.isoformat(), cutoff_day.isoformat()),
        ).fetchall()
        complete = [row for row in snapshots if row["status"] == "ok" and row["is_final"]]
        if not complete:
            raise ValueError("当周还没有完整的估值快照")
        latest = complete[-1]
        end = latest["snapshot_date"]
        positions = weekly.positions(conn, end)
        previous = conn.execute(
            """SELECT * FROM daily_portfolio_snapshots
               WHERE snapshot_date < ? AND status = 'ok' AND is_final = 1
               ORDER BY snapshot_date DESC LIMIT 1""",
            (period_start.isoformat(),),
        ).fetchone()
        contributions = {}
        pnl = None
        if previous and len(complete) == len(snapshots) and end == expected_close.isoformat():
            start = previous["snapshot_date"]
            contributions = weekly.attribution(conn, start, end, weekly.positions(conn, start), positions)
            candidate = Decimal(latest["cumulative_pnl_cny"]) - Decimal(previous["cumulative_pnl_cny"])
            if contributions and abs(sum(contributions.values()) - candidate) <= Decimal("0.01"):
                pnl = candidate
            else:
                contributions = {}

    total = Decimal(latest["total_market_value_cny"])
    rows = [{**row, "market_value_cny": Decimal(row["market_value_cny"])} for row in positions.values()]
    allocation = exposure.breakdown(rows)
    if abs(allocation["allocation_total_cny"] - total) > Decimal("0.01"):
        raise ValueError("分项市值与周末快照未对齐")
    assets = [
        {
            "key": f"{row['market']}:{row['code']}",
            "name": row["name"],
            "market_value_cny": row["market_value_cny"],
            "weight": row["market_value_cny"] / total * 100 if total else Decimal(0),
            "floating_pnl_cny": Decimal(row["unrealized_pnl_cny"]),
            "weekly_pnl_cny": contributions.get(row["security_id"]),
            "price_date": row["price_date"],
        }
        for row in sorted(rows, key=lambda item: -item["market_value_cny"])
    ]
    ranked = sorted(assets, key=lambda asset: asset["floating_pnl_cny"], reverse=True)
    weekly_order = sorted(assets, key=lambda asset: -abs(asset["weekly_pnl_cny"] or Decimal(0)))
    screens = {
        "全资产浮盈 Top 5": [asset for asset in ranked if asset["floating_pnl_cny"] > 0][:5],
        "全资产浮亏 Top 5": [asset for asset in reversed(ranked) if asset["floating_pnl_cny"] < 0][:5],
        "周贡献前 5": [asset for asset in weekly_order if asset["weekly_pnl_cny"]][:5],
    }
    signals: dict[str, list[str]] = {}
    for label, candidates in screens.items():
        for asset in candidates:
            signals.setdefault(asset["key"], []).append(label)
    for asset in assets:
        asset["signals"] = signals.get(asset["key"], [])

    return {
        "cutoff": cutoff.isoformat(),
        "start": period_start.isoformat(),
        "end": end,
        "total_cny": total,
        "weekly_pnl_cny": pnl,
        "floating_pnl_cny": Decimal(latest["unrealized_pnl_cny"]),
        "markets": allocation["market"],
        "themes": allocation["industry"],
        "stock_ranks": _stock_ranks(
            assets, {f"{row['market']}:{row['code']}" for row in rows if row["asset_type"] == "STOCK"}
        ),
        "assets": assets,
    }


def _validate_analysis(cutoff_day: date, snapshot: dict, analysis: Analysis) -> None:
    assets = {asset["key"] for asset in snapshot["assets"]}
    finding_ids = {finding.id for finding in analysis.findings}
    if len(finding_ids) != len(analysis.findings) or sorted(finding_ids) != sorted(
        strategy.finding for strategy in analysis.strategies
    ):
        raise ValueError("每条诊断须对应一条调整建议")
    for evidence in analysis.evidence.values():
        if evidence.published_on >= cutoff_day or set(evidence.assets) - assets:
            raise ValueError(f"披露日期或覆盖标的无效：{evidence.title}")
    for item in [*analysis.findings, *analysis.outside, *analysis.deferred]:
        if set(item.evidence) - analysis.evidence.keys():
            raise ValueError(f"证据引用不存在：{item.title}")
    for finding in analysis.findings:
        if set(finding.assets) - assets or (finding.scope == "个股" and not finding.evidence):
            raise ValueError(f"个股或证据未核实：{finding.title}")
    for candidate in analysis.deferred:
        if set(candidate.assets) - assets:
            raise ValueError(f"候选标的不在本期持仓中：{candidate.title}")


def publish(cutoff_day: date, analysis: Analysis, *, keep_snapshot: bool = False) -> None:
    snapshot = None if keep_snapshot else scan_week(cutoff_day)
    published_at = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    with weekly.archive() as conn:
        _ensure_diagnosis_archive(conn)
        if keep_snapshot:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM diagnosis_editions WHERE cutoff = ?", (cutoff_day.isoformat(),)).fetchone()
            if row is None:
                raise ValueError("找不到要修订的周报")
            snapshot = json.loads(row[0])["snapshot"]
        _validate_analysis(cutoff_day, snapshot, analysis)
        payload = {"snapshot": snapshot, "analysis": analysis.model_dump(mode="json")}
        encoded = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
        conn.execute(
            """INSERT INTO diagnosis_editions (cutoff, payload, published_at)
               VALUES (?, ?, ?)
               ON CONFLICT(cutoff) DO UPDATE SET
                 payload = excluded.payload, published_at = excluded.published_at
               WHERE diagnosis_editions.payload != excluded.payload""",
            (cutoff_day.isoformat(), encoded, published_at),
        )


def _ensure_diagnosis_archive(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS diagnosis_editions (
             cutoff TEXT PRIMARY KEY,
             payload TEXT NOT NULL,
             published_at TEXT NOT NULL
           )"""
    )


def read_report(cutoff: date | None = None) -> dict:
    with weekly.archive() as conn:
        _ensure_diagnosis_archive(conn)
        rows = conn.execute(
            "SELECT cutoff, published_at FROM diagnosis_editions ORDER BY cutoff"
        ).fetchall()
        editions = [
            {"cutoff": day, "number": number, "published_at": published_at}
            for number, (day, published_at) in enumerate(rows, 1)
        ]
        if not editions:
            return {"editions": [], "report": None}
        selected_day = cutoff.isoformat() if cutoff else editions[-1]["cutoff"]
        selected = next((item for item in editions if item["cutoff"] == selected_day), None)
        if selected is None:
            raise ValueError("这期新版周报尚未发布")
        payload = conn.execute(
            "SELECT payload FROM diagnosis_editions WHERE cutoff = ?", (selected_day,)
        ).fetchone()[0]
    report = json.loads(payload)
    snapshot = report["snapshot"]
    if "stock_ranks" not in snapshot:
        stock_keys: set[str] = set()
        if snapshot["assets"]:
            with storage.get_connection() as conn:
                stock_keys = {
                    f"{market}:{code}" for market, code in
                    conn.execute("SELECT market, code FROM securities WHERE asset_type = 'STOCK'")
                }
        snapshot["stock_ranks"] = _stock_ranks(snapshot["assets"], stock_keys)
    return {"editions": editions[::-1], "report": {**selected, **report}}
