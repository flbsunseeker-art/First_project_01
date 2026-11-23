"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiGet, apiSend } from "../lib/api";
import { formatMoney, formatPercent, pnlClass, toNumber } from "../lib/format";
import type { BenchmarkComparison, MarketRefresh, Overview, PerformanceHistory, ReturnPeriod } from "../lib/types";
import { SeriesChart } from "./series-chart";
import { Badge, Card } from "./ui";

const periods: { id: ReturnPeriod; label: string }[] = [
  { id: "today", label: "今日" },
  { id: "year", label: "本年" },
  { id: "last_year", label: "去年" },
  { id: "rolling_year", label: "近一年" },
];

const indices = [
  { id: "csi300", label: "沪深 300", color: "#ffbf60" },
  { id: "csi500", label: "中证 500", color: "#ba9aff" },
] as const;
const mySeries = { label: "我的组合", color: "var(--accent-cyan)" };
const valueRanges = [
  { months: 1, label: "近一个月" },
  { months: 3, label: "近三个月" },
  { months: 6, label: "近半年" },
  { months: 12, label: "近一年" },
];

function monthsBefore(date: string, months: number) {
  const [year, month, day] = date.split("-").map(Number);
  const targetMonth = month - 1 - months;
  const lastDay = new Date(Date.UTC(year, targetMonth + 1, 0)).getUTCDate();
  return new Date(Date.UTC(year, targetMonth, Math.min(day, lastDay))).toISOString().slice(0, 10);
}

export function OverviewMetrics({
  snapshot, history,
}: { snapshot: Overview; history: PerformanceHistory | null }) {
  const router = useRouter();
  const [period, setPeriod] = useState<ReturnPeriod>("today");
  const [refresh, setRefresh] = useState<MarketRefresh | null>(null);
  const [statusUnavailable, setStatusUnavailable] = useState(false);
  const [starting, setStarting] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const abort = new AbortController();
    let timer: number | undefined;
    let wasRunning = attempt > 0;
    async function poll() {
      try {
        const signal = AbortSignal.any([abort.signal, AbortSignal.timeout(5_000)]);
        const data = await apiGet<MarketRefresh>("/api/v1/data/refresh", signal);
        if (abort.signal.aborted) return;
        setStatusUnavailable(false);
        setRefresh(data);
        if (data.status === "running") {
          wasRunning = true;
          timer = window.setTimeout(() => void poll(), 1000);
        } else if (wasRunning) {
          router.refresh();
        }
      } catch {
        if (!abort.signal.aborted) setStatusUnavailable(true);
      }
    }
    void poll();
    return () => {
      abort.abort();
      window.clearTimeout(timer);
    };
  }, [attempt, router]);

  async function retry() {
    setStarting(true);
    try {
      const data = await apiSend<MarketRefresh>("POST", "/api/v1/data/refresh");
      setStatusUnavailable(false);
      setRefresh(data);
      setAttempt((value) => value + 1);
    } catch {
      setStatusUnavailable(true);
    } finally {
      setStarting(false);
    }
  }

  const live = refresh?.overview;
  const overview = live ?? snapshot;
  const quoteRange = overview.quote_through &&
    (overview.quote_from && overview.quote_from !== overview.quote_through
      ? `${overview.quote_from} 至 ${overview.quote_through}` : overview.quote_through);
  const source = overview.snapshot_date
    ? `快照 · ${overview.snapshot_date}` : quoteRange ? `行情 · ${quoteRange}`
      : overview.updated_at ? `估值于 ${overview.updated_at}` : "暂无估值";
  const selected = history?.periods[period];
  const realtime = period === "today" && live?.today_pnl_cny != null;
  const label = periods.find((item) => item.id === period)!.label;
  const pnl = realtime ? live.today_pnl_cny : selected?.pnl;
  const rate = realtime ? live.today_pnl_pct : selected?.return_pct;
  const periodSource = realtime ? live.valuation_date : selected?.from_date && selected.through
    ? `${selected.partial ? "部分区间 · " : ""}${selected.from_date}${selected.through === selected.from_date ? "" : ` 至 ${selected.through}`}`
    : "暂无区间数据";
  const refreshing = starting || (!statusUnavailable && (!refresh || refresh.status === "running"));
  const message = refreshing
    ? (refresh?.phase === "history" ? "最新可用行情已读取，正在补齐收盘快照…" : "正在核对最新行情及基金净值…")
    : statusUnavailable ? "暂时无法读取刷新状态。"
    : refresh?.status === "offline" ? "离线模式 · 使用本地数据。"
    : refresh?.status === "ok" ? "行情刷新已完成。"
    : refresh?.status === "idle" ? "可手动刷新行情。"
    : live ? "本次刷新有部分数据未能更新。"
    : snapshot.snapshot_date ? "暂未取得完整的新估值，已保留最近完整快照。"
    : "暂未取得可用的组合估值。";

  return (
    <section aria-label="资产指标">
      <div className="metric-grid overview-metrics">
        {[
          { label: "总资产市值", value: formatMoney(overview.total_market_value_cny), tone: null },
          { label: "总资产成本", value: formatMoney(overview.total_cost_cny), tone: null },
          { label: "累计收益金额", value: formatMoney(overview.total_pnl_cny, { signed: true }), tone: overview.total_pnl_cny },
          { label: "累计收益率", value: formatPercent(overview.total_pnl_pct, { signed: true }), tone: overview.total_pnl_pct },
        ].map((metric) => (
          <Card className="metric-card" key={metric.label}>
            <span>{metric.label}</span>
            <strong className={pnlClass(metric.tone)}>{metric.value}</strong>
            <small>{source}</small>
          </Card>
        ))}
        <Card className="metric-card metric-window-card">
          <div className="metric-period-heading">
            <span>{label}收益金额</span>
            <select className="period-select" aria-label="收益统计周期" value={period}
              onChange={(event) => setPeriod(event.target.value as ReturnPeriod)}>
              {periods.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
            </select>
          </div>
          <strong className={pnlClass(pnl)}>{formatMoney(pnl, { signed: true })}</strong>
          <small>{periodSource}</small>
        </Card>
        <Card className="metric-card metric-window-card">
          <div className="metric-period-heading"><span>{label}收益率</span></div>
          <strong className={pnlClass(rate)}>{formatPercent(rate, { signed: true })}</strong>
          <small>{periodSource}</small>
        </Card>
      </div>
      <div className="overview-sync" role="status">
        <span>{message}</span>
        {!refreshing && refresh?.status !== "offline" && (
          <button className="button button-ghost" type="button" onClick={() => void retry()}>刷新行情</button>
        )}
        {!refreshing && Boolean(refresh?.warnings.length) && (
          <details>
            <summary>查看刷新详情</summary>
            <ul>{refresh?.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </details>
        )}
      </div>
    </section>
  );
}

export function ValueChart({ history }: { history: PerformanceHistory }) {
  const [months, setMonths] = useState(1);
  const last = history.days.filter((day) => day.market_value !== null).at(-1);
  const from = last ? monthsBefore(last.date, months) : null;
  const days = last && from ? history.days.filter((day) => day.date >= from && day.date <= last.date) : [];
  const first = days.find((day) => day.market_value !== null);
  const showsPartialCoverage = first && history.fund_coverage_from && first.date < history.fund_coverage_from;
  const points = days.map((day) => ({
    label: day.date.slice(5), date: day.date, values: [toNumber(day.market_value)],
    detail: day.market_value === null ? "当日快照不完整"
      : history.fund_coverage_from && day.date < history.fund_coverage_from ? "场外基金尚未纳入" : undefined,
  }));
  return (
    <Card className="chart-card">
      <div className="section-heading value-chart-heading">
        <h2>总资产市值趋势</h2>
        <div className="segmented-control" role="group" aria-label="总资产市值趋势周期">
          {valueRanges.map((range) => (
            <button type="button" key={range.months} aria-pressed={months === range.months}
              onClick={() => setMonths(range.months)}>{range.label}</button>
          ))}
        </div>
      </div>
      {first && last && <p className="chart-period" aria-live="polite">{first.date} 至 {last.date} · 人民币</p>}
      <SeriesChart key={months} points={points} series={[{ label: "总市值", color: "var(--accent-cyan)" }]}
        label="总资产市值趋势" markerDate={history.fund_coverage_from} />
      {showsPartialCoverage &&
        <p className="chart-note">场外基金自 {history.fund_coverage_from} 纳入估值。此前为当时已记录的资产。</p>}
    </Card>
  );
}

export function BenchmarkChart({ comparison }: { comparison: BenchmarkComparison }) {
  const [enabled, setEnabled] = useState({ csi300: true, csi500: true });
  const selected = indices.filter((item) => enabled[item.id]);
  const last = comparison.points.at(-1);
  const points = comparison.points.map((point) => ({
    label: point.date.slice(5), date: point.date,
    values: [toNumber(point.portfolio), ...selected.map((item) => toNumber(point[item.id]))],
  }));

  return (
    <Card className="chart-card">
      <div className="section-heading">
        <h2>持仓组合与指数对比</h2>
        <Badge>累计收益率</Badge>
      </div>
      {comparison.from_date && <p className="chart-period">
        {comparison.from_date} 至 {comparison.through}{comparison.partial ? " · 部分快照缺失" : ""}
      </p>}
      {last && <div className="benchmark-metrics">
        <div>
          <span className="benchmark-series-label">
            <i aria-hidden="true" style={{ background: mySeries.color }} />{mySeries.label}
          </span>
          <strong className={pnlClass(last.portfolio)}>{formatPercent(last.portfolio, { signed: true })}</strong>
        </div>
        {indices.map((item) => {
          const delta = toNumber(comparison.excess[item.id]);
          const rounded = delta === null ? null : Number(delta.toFixed(2));
          return <div key={item.id}>
            <span className="benchmark-series-label">
              <i aria-hidden="true" style={{ background: item.color }} />{item.label}
            </span>
            <strong className={pnlClass(last[item.id])}>{formatPercent(last[item.id], { signed: true })}</strong>
            <small className="benchmark-excess">
              <span>跑赢指数</span>
              <b className={pnlClass(rounded)}>{formatPercent(rounded, { signed: rounded !== 0 })}</b>
            </small>
          </div>;
        })}
      </div>}
      <SeriesChart points={points} series={[mySeries, ...selected]} unit="percent" label="持仓组合与指数对比" />
      <div className="series-legend" aria-label="图表图例">
        <span><i style={{ background: mySeries.color }} />我的组合</span>
        {indices.map((item) => (
          <button type="button" aria-pressed={enabled[item.id]} key={item.id}
            onClick={() => setEnabled((current) => ({ ...current, [item.id]: !current[item.id] }))}>
            <i style={{ background: item.color }} />{item.label}
          </button>
        ))}
      </div>
      <p className="chart-note">组合收益已剔除资金进出，指数采用价格指数收盘值。</p>
    </Card>
  );
}
