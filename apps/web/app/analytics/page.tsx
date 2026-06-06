import { AppShell } from "../../components/app-shell";
import { Badge, Card, DataTable } from "../../components/ui";
import { apiGet } from "../../lib/api";
import { fallbackDailyReturns } from "../../lib/fallback-data";
import { formatMoney, pnlClass } from "../../lib/format";
import type { DailyReturn } from "../../lib/types";

export const dynamic = "force-dynamic";

async function loadReturns() {
  try {
    return await apiGet<DailyReturn[]>("/api/v1/analytics/daily-returns");
  } catch {
    return fallbackDailyReturns;
  }
}

export default async function AnalyticsPage() {
  const returns = await loadReturns();
  const latest = returns.slice(-31);

  return (
    <AppShell>
      <main className="dashboard">
        <section className="page-heading">
          <Badge tone="info">Analytics</Badge>
          <h2>收益分析</h2>
          <p>每日盈亏、累计收益和股票总市值趋势使用同一套快照数据。</p>
        </section>

        <Card>
          <div className="section-heading">
            <h2>收益日历</h2>
            <Badge>{latest.length ? "最近 31 天" : "暂无快照"}</Badge>
          </div>
          <div className="return-calendar">
            {latest.map((row) => (
              <div className="return-day" key={row.snapshot_date}>
                <span>{row.snapshot_date.slice(5)}</span>
                <b className={pnlClass(row.daily_pnl_cny)}>
                  {formatMoney(row.daily_pnl_cny, { signed: true })}
                </b>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="section-heading">
            <h2>趋势明细</h2>
            <Badge>Snapshot</Badge>
          </div>
          <DataTable
            columns={["日期", "总市值", "累计收益", "当日盈亏", "状态"]}
            rows={returns.slice(-20).reverse().map((row) => [
              row.snapshot_date,
              formatMoney(row.total_market_value_cny),
              <span className={pnlClass(row.cumulative_pnl_cny)} key="cumulative">
                {formatMoney(row.cumulative_pnl_cny, { signed: true })}
              </span>,
              <span className={pnlClass(row.daily_pnl_cny)} key="daily">
                {formatMoney(row.daily_pnl_cny, { signed: true })}
              </span>,
              row.status,
            ])}
          />
        </Card>
      </main>
    </AppShell>
  );
}
