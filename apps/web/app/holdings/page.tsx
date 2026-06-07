import { AppShell } from "../../components/app-shell";
import { AllocationPie } from "../../components/charts";
import { HoldingsTable } from "../../components/holdings-table";
import { Badge, Card } from "../../components/ui";
import { apiGet } from "../../lib/api";
import { fallbackHoldings } from "../../lib/fallback-data";
import { formatMoney, formatPercent, pnlClass } from "../../lib/format";
import type { HoldingsSummary } from "../../lib/types";

export const dynamic = "force-dynamic";

async function loadHoldings() {
  try {
    return await apiGet<HoldingsSummary>("/api/v1/holdings/summary");
  } catch {
    return { holdings: fallbackHoldings, industry: [], market: [] };
  }
}

export default async function HoldingsPage() {
  const { holdings, industry, market } = await loadHoldings();

  return (
    <AppShell>
      <main className="dashboard">
        <section className="page-heading">
          <Badge tone="info">Holdings</Badge>
          <h2>当前持仓</h2>
          <p>持仓明细支持全局排序，默认按 A 股、港股、美股归类展示。</p>
        </section>

        <Card>
          <HoldingsTable holdings={holdings} />
        </Card>

        <section className="mobile-card-list">
          {holdings.map((row) => (
            <Card className="holding-mobile-card" key={`${row.market}-${row.code}`}>
              <div>
                <strong>{row.name}</strong>
                <span>{row.market} · {row.code} · {row.industry}</span>
              </div>
              <b className={pnlClass(row.unrealized_pnl_cny)}>
                {formatMoney(row.unrealized_pnl_cny, { signed: true })} ·{" "}
                {formatPercent(row.position_pct)}
              </b>
            </Card>
          ))}
        </section>

        <section className="panel-grid">
          <Card>
            <div className="section-heading">
              <h2>行业分布</h2>
              <Badge>{industry.length} 类</Badge>
            </div>
            <AllocationPie items={industry} labelKey="industry" />
          </Card>

          <Card>
            <div className="section-heading">
              <h2>市场分布</h2>
              <Badge>{market.length} 个市场</Badge>
            </div>
            <AllocationPie items={market} labelKey="market" />
          </Card>
        </section>
      </main>
    </AppShell>
  );
}
