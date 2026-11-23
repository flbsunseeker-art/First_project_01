import { Suspense } from "react";
import { LoadingPanel } from "../components/app-shell";
import { LoadError } from "../components/load-state";
import { BenchmarkChart, OverviewMetrics, ValueChart } from "../components/overview-panels";
import { ReturnCalendar } from "../components/return-calendar";
import { Card } from "../components/ui";
import { apiGet } from "../lib/api";
import type { BenchmarkComparison, CalendarHistory, Overview, PerformanceHistory } from "../lib/types";

export const dynamic = "force-dynamic";

async function Metrics({ history }: { history: Promise<PerformanceHistory | null> }) {
  const [snapshot, report] = await Promise.all([
    apiGet<Overview>("/api/v1/overview?snapshot_only=true").catch(() => ({ status: "unavailable" })),
    history,
  ]);
  return <OverviewMetrics snapshot={snapshot} history={report} />;
}

async function Value({ history }: { history: Promise<PerformanceHistory | null> }) {
  const report = await history;
  return report ? <ValueChart history={report} /> : <Card><LoadError message="总市值趋势暂不可用。" /></Card>;
}

async function Benchmark() {
  const report = await apiGet<BenchmarkComparison>("/api/v1/analytics/benchmarks")
    .catch(() => null);
  return report?.points.length ? <BenchmarkChart comparison={report} /> :
    <Card className="chart-card">
      <h2>持仓组合与指数对比</h2>
      <LoadError message={report ? "指数行情或共同区间数据不足。" : "指数数据暂不可用。"} />
    </Card>;
}

type HomeParams = Promise<{ month?: string }>;

async function Returns({ history, searchParams }: {
  history: Promise<CalendarHistory | null>;
  searchParams: HomeParams;
}) {
  const [report, params] = await Promise.all([history, searchParams]);
  return report
    ? <ReturnCalendar history={report} initialMonth={params.month} />
    : <LoadError message="收益日历暂不可用。" />;
}

export default function Home({ searchParams }: { searchParams: HomeParams }) {
  const history = apiGet<CalendarHistory>("/api/v1/analytics/performance?calendar=true").catch(() => null);
  return (
    <main className="dashboard">
      <header className="page-heading home-heading">
        <h1>持仓总览</h1>
      </header>
      <Suspense fallback={<LoadingPanel label="正在读取资产快照…" />}><Metrics history={history} /></Suspense>
      <Suspense fallback={<LoadingPanel label="正在读取总市值趋势…" />}><Value history={history} /></Suspense>
      <Suspense fallback={<LoadingPanel label="正在读取指数行情…" />}><Benchmark /></Suspense>
      <Card className="returns-section" id="returns">
        <div className="section-heading"><h2>收益日历</h2></div>
        <Suspense fallback={<LoadingPanel label="正在读取收益日历…" />}>
          <Returns history={history} searchParams={searchParams} />
        </Suspense>
      </Card>
    </main>
  );
}
