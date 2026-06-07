import { AppShell } from "../../components/app-shell";
import { MonthSwitcher } from "../../components/month-switcher";
import { Badge, Card, DataTable } from "../../components/ui";
import { apiGet } from "../../lib/api";
import { fallbackDailyReturns } from "../../lib/fallback-data";
import { formatMoney, pnlClass, toNumber } from "../../lib/format";
import type { DailyReturn } from "../../lib/types";

export const dynamic = "force-dynamic";

async function loadReturns() {
  try {
    return await apiGet<DailyReturn[]>("/api/v1/analytics/daily-returns");
  } catch {
    return fallbackDailyReturns;
  }
}

function monthKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function parseMonth(value: string | undefined, returns: DailyReturn[]) {
  if (value && /^\d{4}-\d{2}$/.test(value)) {
    return value;
  }
  const latest = returns[returns.length - 1]?.snapshot_date;
  return latest ? latest.slice(0, 7) : monthKey(new Date());
}

function monthCells(month: string, returns: DailyReturn[]) {
  const [year, monthNumber] = month.split("-").map(Number);
  const first = new Date(year, monthNumber - 1, 1);
  const days = new Date(year, monthNumber, 0).getDate();
  const offset = first.getDay();
  const byDate = new Map(returns.map((row) => [row.snapshot_date, row]));
  const cells: Array<{ date?: string; day?: number; row?: DailyReturn }> = [];
  for (let index = 0; index < offset; index += 1) {
    cells.push({});
  }
  for (let day = 1; day <= days; day += 1) {
    const date = `${month}-${String(day).padStart(2, "0")}`;
    cells.push({ date, day, row: byDate.get(date) });
  }
  return cells;
}

export default async function AnalyticsPage({
  searchParams,
}: Readonly<{ searchParams?: Promise<{ month?: string }> }>) {
  const returns = await loadReturns();
  const params = await searchParams;
  const month = parseMonth(params?.month, returns);
  const cells = monthCells(month, returns);
  const monthRows = returns.filter((row) => row.snapshot_date.startsWith(month));
  const monthPnl = monthRows.reduce((sum, row) => sum + (toNumber(row.daily_pnl_cny) ?? 0), 0);
  const profitDays = monthRows.filter((row) => (toNumber(row.daily_pnl_cny) ?? 0) > 0).length;
  const lossDays = monthRows.filter((row) => (toNumber(row.daily_pnl_cny) ?? 0) < 0).length;

  return (
    <AppShell>
      <main className="dashboard">
        <section className="page-heading">
          <Badge tone="info">Analytics</Badge>
          <h2>收益分析</h2>
          <p>每日盈亏、累计收益和股票总市值趋势使用同一套快照数据。</p>
        </section>

        <div className="calendar-headline">
          <div className="calendar-summary">
            <Badge tone="info">数据状态：已更新</Badge>
            <Badge tone={monthPnl >= 0 ? "profit" : "loss"}>
              本月累计 {formatMoney(monthPnl, { signed: true })}
            </Badge>
            <Badge>盈利 {profitDays} 天</Badge>
            <Badge>亏损 {lossDays} 天</Badge>
          </div>
          <MonthSwitcher month={month} />
        </div>

        <Card>
          <div className="section-heading">
            <h2>收益日历</h2>
            <Badge>{monthRows.length ? `${monthRows.length} 个快照` : "暂无快照"}</Badge>
          </div>
          <div className="weekday-row">
            {["日", "一", "二", "三", "四", "五", "六"].map((day) => (
              <span key={day}>周{day}</span>
            ))}
          </div>
          <div className="return-calendar">
            {cells.map((cell, index) => (
              <div
                className={`return-day ${cell.row ? "has-value" : ""}`}
                key={cell.date ?? `blank-${index}`}
              >
                {cell.date ? (
                  <>
                    <span>{cell.day}</span>
                    <b className={pnlClass(cell.row?.daily_pnl_cny)}>
                      {cell.row ? formatMoney(cell.row.daily_pnl_cny, { signed: true }) : "-"}
                    </b>
                  </>
                ) : null}
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
            columns={["日期", "总市值", "累计收益", "当日盈亏"]}
            rows={monthRows.slice(-20).reverse().map((row) => [
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
      </main>
    </AppShell>
  );
}
