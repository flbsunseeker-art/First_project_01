import { AppShell } from "../../components/app-shell";
import { IndustryEditor } from "../../components/industry-actions";
import { Badge, Card, DataTable } from "../../components/ui";
import { apiGet } from "../../lib/api";
import { fallbackHoldings } from "../../lib/fallback-data";
import { formatMoney, pnlClass } from "../../lib/format";
import type { Allocation, Holding } from "../../lib/types";

export const dynamic = "force-dynamic";

async function loadHoldings() {
  try {
    const [holdings, industry, market] = await Promise.all([
      apiGet<Holding[]>("/api/v1/holdings"),
      apiGet<Allocation[]>("/api/v1/holdings/allocation/industry"),
      apiGet<Allocation[]>("/api/v1/holdings/allocation/market"),
    ]);
    return { holdings, industry, market };
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
          <p>股数、成本、市值、盈亏、市场和行业都来自后端统一核算结果。</p>
        </section>

        <Card>
          <DataTable
            columns={["市场", "名称", "代码", "行业", "股数", "成本", "市值", "盈亏", "行业编辑"]}
            rows={holdings.map((row) => [
              row.market,
              row.name,
              row.code,
              row.industry,
              row.shares,
              formatMoney(row.cost_value_cny),
              formatMoney(row.market_value_cny),
              <span className={pnlClass(row.unrealized_pnl_cny)} key={row.code}>
                {formatMoney(row.unrealized_pnl_cny, { signed: true })}
              </span>,
              <IndustryEditor
                defaultIndustry={row.industry}
                key={`${row.id}-industry`}
                securityId={row.id}
              />,
            ])}
          />
        </Card>

        <section className="mobile-card-list">
          {holdings.map((row) => (
            <Card className="holding-mobile-card" key={`${row.market}-${row.code}`}>
              <div>
                <strong>{row.name}</strong>
                <span>{row.market} · {row.code} · {row.industry}</span>
              </div>
              <b className={pnlClass(row.unrealized_pnl_cny)}>
                {formatMoney(row.unrealized_pnl_cny, { signed: true })}
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
            <div className="allocation-list">
              {industry.map((item) => (
                <span key={item.industry}>
                  {item.industry} · {formatMoney(item.market_value_cny)} · {item.position_pct}%
                </span>
              ))}
            </div>
          </Card>

          <Card>
            <div className="section-heading">
              <h2>市场分布</h2>
              <Badge>{market.length} 个市场</Badge>
            </div>
            <div className="allocation-list">
              {market.map((item) => (
                <span key={item.market}>
                  {item.market} · {formatMoney(item.market_value_cny)} · {item.position_pct}%
                </span>
              ))}
            </div>
          </Card>
        </section>
      </main>
    </AppShell>
  );
}
