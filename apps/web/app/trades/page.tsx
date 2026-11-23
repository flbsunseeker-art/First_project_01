import { Suspense } from "react";
import { LoadingPanel } from "../../components/app-shell";
import { LoadError } from "../../components/load-state";
import { Card, DataTable, Quantity } from "../../components/ui";
import { apiGet } from "../../lib/api";
import { formatUnitPrice } from "../../lib/format";
import type { Trade } from "../../lib/types";

export const dynamic = "force-dynamic";

type DataStatus = {
  complete_snapshot_through: string | null;
  latest_snapshot: { snapshot_date: string; status: string; is_final: number } | null;
  latest_sync: { started_at: string; finished_at: string | null; status: string } | null;
};

const syncLabels: Record<string, string> = {
  ok: "已完成",
  partial: "部分数据待补齐",
  failed: "同步失败",
  running: "进行中",
};

const recentTradeLimit = 15;

function TradeTable({ trades }: { trades: Trade[] }) {
  return (
    <DataTable
      columns={["交易日期", "方向", "市场", "代码", "名称", "股数 / 份额", "成交价 / 净值", "说明"]}
      rows={trades.map((trade) => [
        trade.trade_date, trade.side === "BUY" ? "买入" : "卖出", trade.market, trade.code,
        trade.name, <Quantity key={trade.id} value={trade.shares} />,
        `${formatUnitPrice(trade.price, trade.asset_type)} ${trade.currency}`,
        [trade.reason_category, trade.note].filter(Boolean).join(" · ") || "—",
      ])}
    />
  );
}

async function History() {
  const trades = await apiGet<Trade[]>("/api/v1/trades").catch(() => null);
  const olderTrades = trades?.slice(recentTradeLimit) ?? [];
  return <Card className="trade-history">
    <div className="section-heading">
      <h2>交易记录</h2>
      {trades?.[0] && <small className="muted-copy">最近交易日 · {trades[0].trade_date}</small>}
    </div>
    {trades?.length ? (
      <>
        <TradeTable trades={trades.slice(0, recentTradeLimit)} />
        {olderTrades.length > 0 && (
          <details className="trade-history-older">
            <summary>
              <span className="trade-history-expand">展开更早的 {olderTrades.length} 条交易</span>
              <span className="trade-history-collapse">收起更早的交易</span>
            </summary>
            <TradeTable trades={olderTrades} />
          </details>
        )}
      </>
    ) : trades ? <p className="muted-copy">暂无交易记录</p> : <LoadError message="交易记录暂不可用。" />}
  </Card>;
}

async function LedgerDataStatus() {
  const data = await apiGet<DataStatus>("/api/v1/data/status").catch(() => null);
  const latest = data?.latest_snapshot;
  const sync = data?.latest_sync;
  return (
    <Card className="trade-data-status">
      <div className="section-heading"><h2>数据状态</h2></div>
      {data ? (
        <>
          <dl>
            <div>
              <dt>完整估值截至</dt>
              <dd>{data.complete_snapshot_through ?? "暂无完整估值"}</dd>
            </div>
            <div>
              <dt>最近一次行情与快照同步</dt>
              <dd>{sync ? <>{(sync.finished_at ?? sync.started_at).replace("T", " ").slice(0, 16)} <small>· {syncLabels[sync.status] ?? "状态待确认"}</small></> : "暂无同步记录"}</dd>
            </div>
          </dl>
          {latest && (latest.status !== "ok" || !latest.is_final) &&
            <p className="data-status-note">{latest.snapshot_date} 的估值待补齐，暂未计入收益趋势。</p>}
        </>
      ) : <LoadError message="暂时无法读取数据状态。" />}
    </Card>
  );
}

export default function TradesPage() {
  return (
    <main className="dashboard">
      <header className="page-heading">
        <h1>交易流水</h1>
      </header>
      <Suspense fallback={<LoadingPanel label="正在读取交易记录…" />}><History /></Suspense>
      <Suspense fallback={<LoadingPanel label="正在读取数据状态…" />}><LedgerDataStatus /></Suspense>
    </main>
  );
}
