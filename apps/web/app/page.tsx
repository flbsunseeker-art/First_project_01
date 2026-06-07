import { AppShell } from "../components/app-shell";
import { TrendDetailList, TrendLineChart } from "../components/charts";
import { Badge, Card } from "../components/ui";
import { apiGet } from "../lib/api";
import { fallbackDailyReturns, fallbackOverview } from "../lib/fallback-data";
import { formatMoney, formatPercent, pnlClass } from "../lib/format";
import type { DailyReturn, Overview } from "../lib/types";

export const dynamic = "force-dynamic";

async function loadOverview() {
  try {
    const [overview, trend] = await Promise.all([
      apiGet<Overview>("/api/v1/overview"),
      apiGet<DailyReturn[]>("/api/v1/analytics/value-trend?start_date=2026-05-11"),
    ]);
    return { overview, trend };
  } catch {
    return { overview: fallbackOverview, trend: fallbackDailyReturns };
  }
}

export default async function Home() {
  const { overview, trend } = await loadOverview();
  const latestRows = trend.slice(-7).reverse();

  return (
    <AppShell>
      <main className="dashboard">
        <section className="product-hero">
          <div>
            <Badge tone="info">Stockpilot</Badge>
            <h1>Stockpilot</h1>
            <p>
              聚合 A 股、港股、美股持仓，统一追踪收益、仓位与行业分布，
              并提供面向市场趋势的持仓洞察。
            </p>
          </div>
          <div className="hero-updated">
            <span>数据更新</span>
            <strong>{overview.updated_at ?? "等待数据"}</strong>
          </div>
        </section>

        <section className="metric-grid" aria-label="portfolio overview">
          {[
            { label: "总持仓市值", value: formatMoney(overview.total_market_value_cny), tone: null },
            { label: "总持仓成本", value: formatMoney(overview.total_cost_cny), tone: null },
            {
              label: "累计收益金额",
              value: formatMoney(overview.total_pnl_cny, { signed: true }),
              tone: overview.total_pnl_cny,
            },
            {
              label: "累计收益率",
              value: formatPercent(overview.total_pnl_pct, { signed: true }),
              tone: overview.total_pnl_pct,
            },
            {
              label: "今日收益金额",
              value: formatMoney(overview.today_pnl_cny, { signed: true }),
              tone: overview.today_pnl_cny,
            },
            {
              label: "今日收益率",
              value: formatPercent(overview.today_pnl_pct, { signed: true }),
              tone: overview.today_pnl_pct,
            },
          ].map((metric) => (
            <Card className="metric-card" key={metric.label}>
              <span>{metric.label}</span>
              <strong className={pnlClass(metric.tone)}>{metric.value}</strong>
              <small>{overview.updated_at ?? "等待数据"}</small>
            </Card>
          ))}
        </section>

        <Card className="trend-panel">
          <div className="section-heading">
            <h2>总市值变化趋势</h2>
            <Badge>{trend.length ? "2026-05-11 至今" : "No snapshots"}</Badge>
          </div>
          <div className="trend-layout">
            <TrendLineChart rows={trend} />
            <TrendDetailList rows={latestRows} />
          </div>
        </Card>

        <section className="panel-grid">
          <Card>
            <div className="section-heading">
              <h2>数据更新时间</h2>
              <Badge tone={overview.status === "ok" ? "info" : "warning"}>
                {overview.status}
              </Badge>
            </div>
            <p>{overview.updated_at ?? "等待数据"}</p>
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
