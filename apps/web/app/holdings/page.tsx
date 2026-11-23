import { Suspense } from "react";
import { LoadingPanel } from "../../components/app-shell";
import { AllocationPie } from "../../components/charts";
import { HoldingsTable } from "../../components/holdings-table";
import { LoadError } from "../../components/load-state";
import { Badge, Card } from "../../components/ui";
import { apiGet } from "../../lib/api";
import { formatMoney, formatPercent, toNumber } from "../../lib/format";
import type { HoldingsSummary } from "../../lib/types";

export const dynamic = "force-dynamic";

function UnresolvedMarkets({ items }: { items: HoldingsSummary["unresolved_market"] }) {
  if (!items?.length) return null;
  return (
    <section className="unresolved-markets" aria-labelledby="unresolved-market-title">
      <h3 id="unresolved-market-title">「其他／待核实」包含什么？</h3>
      <p>以下持仓金额尚未归入三个市场，仍计入总市值。</p>
      <ul>
        {items.map((item) => (
          <li key={`${item.market}-${item.code}`}>
            <div>
              <strong>{item.name}</strong>
              <small>{item.code} · {item.reason}
                {(toNumber(item.holding_pct) ?? 0) < 100 ? `（占该持仓 ${formatPercent(item.holding_pct)}）` : ""}
              </small>
            </div>
            <b>{formatMoney(item.market_value_cny)} 元</b>
          </li>
        ))}
      </ul>
    </section>
  );
}

async function HoldingsContent() {
  const summary = await apiGet<HoldingsSummary>("/api/v1/holdings/summary?cached_only=true").catch(() => null);
  if (!summary) return <Card><LoadError message="当前持仓暂不可用。" /></Card>;
  const { holdings, industry, market, investment_plans: plans } = summary;
  const dailyTotal = plans.reduce((sum, plan) => sum + Number(plan.amount_cny), 0);
  const dateLabel = summary.quote_through
    ? `${summary.quote_from === summary.quote_through ? summary.quote_through : `${summary.quote_from} 至 ${summary.quote_through}`}`
    : "暂无行情";
  return (
    <>
      <p className="muted-copy">本地行情和净值 · {dateLabel}</p>
      {summary.missing.length > 0 && <LoadError message={`部分资产无法估值：${summary.missing.join("、")}。`} />}
      <HoldingsTable holdings={holdings} />

      <section className="holdings-allocations">
        {summary.missing.length > 0 && <p className="muted-copy">分布仅汇总有估值的资产。</p>}
        <div className="allocation-grid">
          <Card>
            <div className="section-heading"><h2>行业与主题分布</h2><Badge>{industry.length} 类</Badge></div>
            <AllocationPie items={industry} labelKey="industry" />
          </Card>
          <Card>
            <div className="section-heading"><h2>市场分布</h2><Badge>人民币</Badge></div>
            <AllocationPie items={market} labelKey="market" />
            <p className="chart-note allocation-scope">A 股市场沿用境内投向口径，包含境内债券、黄金等。</p>
            <UnresolvedMarkets items={summary.unresolved_market} />
            {summary.market_sources.length > 0 && (
              <details className="allocation-sources">
                <summary>查看基金投向与拆分依据</summary>
                <p>使用公开的指数权重或基金持仓披露估算。</p>
                <p>按本组合的归类口径，交银数据产业、嘉实新能源新材料及易方达蓝筹精选的未划分部分（12.95%）计入 A 股市场。</p>
                <ul>{summary.market_sources.map((item) => <li key={item.url}>
                  <a href={item.url} target="_blank" rel="noreferrer">{item.label}</a> · {item.as_of}
                </li>)}</ul>
              </details>
            )}
          </Card>
        </div>
      </section>

      <Card className="recurring-section">
        <div className="section-heading">
          <h2>每日定投</h2>
          {plans.length > 0 && <Badge>{formatMoney(dailyTotal)} 元 / 交易日</Badge>}
        </div>
        {plans.length > 0 ? <div className="fund-plan-list">
          {plans.map((plan) => <div key={plan.id}>
            <span>{plan.name}</span>
            <small>{plan.code} · 周末跳过</small>
            <strong>{formatMoney(plan.amount_cny)} 元</strong>
          </div>)}
        </div> : <p className="muted-copy">暂无生效计划</p>}
      </Card>
    </>
  );
}

export default function HoldingsPage() {
  return (
    <main className="dashboard">
      <header className="page-heading">
        <h1>持仓明细</h1>
        <p>按交易市场查看明细，按底层投向了解资产分布。</p>
      </header>
      <Suspense fallback={<LoadingPanel label="正在读取持仓…" />}><HoldingsContent /></Suspense>
    </main>
  );
}
