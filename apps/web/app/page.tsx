import { AppShell } from "../components/app-shell";
import { Badge, Button, Card, DataTable } from "../components/ui";
import { apiGet } from "../lib/api";
import { fallbackDailyReturns, fallbackOverview } from "../lib/fallback-data";
import { formatMoney, pnlClass } from "../lib/format";
import type { DailyReturn, Overview } from "../lib/types";

export const dynamic = "force-dynamic";

async function loadOverview() {
  try {
    const [overview, trend] = await Promise.all([
      apiGet<Overview>("/api/v1/overview"),
      apiGet<DailyReturn[]>("/api/v1/analytics/value-trend"),
    ]);
    return { overview, trend };
  } catch {
    return { overview: fallbackOverview, trend: fallbackDailyReturns };
  }
}

export default async function Home() {
  const { overview, trend } = await loadOverview();
  const latestRows = trend.slice(-5).reverse();

  return (
    <AppShell>
      <main className="dashboard">
        <section className="hero-card">
          <div>
            <Badge tone="info">Overview</Badge>
            <h2>把跨市场持仓，收束成一张清醒的本地总账。</h2>
            <p>
              股票总市值、今日盈亏、累计盈亏和数据状态统一来自 FastAPI，
              前端不再直接碰数据库。
            </p>
          </div>
          <div className="hero-actions">
            <Button>同步数据</Button>
            <Button variant="ghost">导出报告</Button>
          </div>
        </section>

        <section className="metric-grid" aria-label="portfolio overview">
          {[
            { label: "总市值 CNY", value: overview.total_market_value_cny, isPnl: false },
            { label: "总成本 CNY", value: overview.total_cost_cny, isPnl: false },
            { label: "总盈亏 CNY", value: overview.total_pnl_cny, isPnl: true },
            { label: "今日盈亏 CNY", value: overview.today_pnl_cny, isPnl: true },
            { label: "已实现盈亏", value: overview.realized_pnl_cny, isPnl: true },
            { label: "未实现盈亏", value: overview.unrealized_pnl_cny, isPnl: true },
          ].map((metric) => (
            <Card className="metric-card" key={metric.label}>
              <span>{metric.label}</span>
              <strong className={pnlClass(metric.isPnl ? metric.value : null)}>
                {formatMoney(metric.value, { signed: metric.isPnl })}
              </strong>
              <small>{overview.updated_at ?? "等待数据"}</small>
            </Card>
          ))}
        </section>

        <section className="panel-grid">
          <Card>
            <div className="section-heading">
              <h2>总市值趋势</h2>
              <Badge>{trend.length ? "Live API" : "No snapshots"}</Badge>
            </div>
            <DataTable
              columns={["日期", "总市值", "累计收益", "当日盈亏"]}
              rows={latestRows.map((row) => [
                row.snapshot_date,
                formatMoney(row.total_market_value_cny),
                <span className={pnlClass(row.cumulative_pnl_cny)} key="cumulative">
                  {formatMoney(row.cumulative_pnl_cny, { signed: true })}
                </span>,
                <span className={pnlClass(row.daily_pnl_cny)} key="daily">
                  {formatMoney(row.daily_pnl_cny, { signed: true })}
                </span>,
              ])}
            />
          </Card>

          <Card className="side-panel">
            <div className="section-heading">
              <h2>数据状态</h2>
              <Badge tone={overview.status === "ok" ? "info" : "warning"}>
                {overview.status}
              </Badge>
            </div>
            <p>
              最新快照：
              {overview.latest_snapshot?.snapshot_date ?? "暂无"}。
              缺失行情：{overview.missing?.length ? overview.missing.join("、") : "无"}。
            </p>
          </Card>
        </section>
      </main>
    </AppShell>
  );
}
