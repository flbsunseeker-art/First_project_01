import { AppShell } from "../../components/app-shell";
import { DeleteTradeButton, TradeForm } from "../../components/trade-actions";
import { Badge, Card, DataTable } from "../../components/ui";
import { apiGet } from "../../lib/api";
import { fallbackTrades } from "../../lib/fallback-data";
import { formatMoney } from "../../lib/format";
import type { Trade } from "../../lib/types";

export const dynamic = "force-dynamic";

async function loadTrades() {
  try {
    return await apiGet<Trade[]>("/api/v1/trades");
  } catch {
    return fallbackTrades;
  }
}

export default async function TradesPage() {
  const trades = await loadTrades();

  return (
    <AppShell>
      <main className="dashboard">
        <section className="page-heading">
          <Badge tone="info">Trades</Badge>
          <h2>手工交易流水</h2>
          <p>买卖记录是持仓推导的真相源；修改交易后后端会触发后续快照重算。</p>
        </section>

        <Card>
          <div className="section-heading">
            <h2>新增交易</h2>
            <Badge tone="warning">Manual</Badge>
          </div>
          <TradeForm />
        </Card>

        <Card>
          <DataTable
            columns={["日期", "方向", "市场", "代码", "名称", "股数", "价格", "理由", "操作"]}
            rows={trades.map((trade) => [
              trade.trade_date,
              trade.side === "BUY" ? "买入" : "卖出",
              trade.market,
              trade.code,
              trade.name,
              trade.shares,
              formatMoney(trade.price),
              trade.reason_category || "-",
              <DeleteTradeButton key={trade.id} tradeId={trade.id} />,
            ])}
          />
        </Card>
      </main>
    </AppShell>
  );
}
