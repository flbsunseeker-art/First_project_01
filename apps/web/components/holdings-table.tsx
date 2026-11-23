"use client";

import { useRef, useState } from "react";
import { formatMoney, formatPercent, formatUnitPrice, pnlClass, toNumber } from "../lib/format";
import type { Holding } from "../lib/types";
import { Badge, Card, Quantity } from "./ui";

const groups = [
  { market: "A", title: "A 股（含场内 ETF）" },
  { market: "HK", title: "港股" },
  { market: "US", title: "美股" },
  { market: "FUND", title: "场外基金" },
];
const columns = [
  ["资产名称", 146], ["代码", 87], ["最新市值 CNY", 125],
  ["累计收益 CNY", 125], ["累计收益率", 105], ["现价 / 净值", 112], ["成本价 / 净值", 112],
  ["今日收益 CNY", 125], ["今日收益率", 105], ["持仓占比", 96], ["持仓股数 / 份额", 128],
  ["持仓成本 CNY", 125], ["币种", 58], ["净值 / 行情日期", 150],
  ["资产类型", 89], ["行业 / 基金分类", 126], ["#", 42],
] as const;
const assetTypes = { STOCK: "股票", ETF: "场内 ETF", MUTUAL_FUND: "场外基金" };
const sortOptions = [
  ["按市值排序", "market_value_cny"], ["按累计收益金额排序", "unrealized_pnl_cny"],
  ["按累计收益率排序", "unrealized_pnl_pct"], ["按今日收益排序", "today_pnl_cny"],
  ["按仓位占比排序", "position_pct"],
] as const;
type SortKey = typeof sortOptions[number][1];
const tableWidth = columns.reduce((sum, [, width]) => sum + width, 0);

function Columns() {
  return <colgroup>{columns.map(([label, width]) => <col key={label} style={{ width }} />)}</colgroup>;
}

function Header() {
  return <thead><tr>{columns.map(([label]) => <th key={label} scope="col">{label}</th>)}</tr></thead>;
}

function HoldingRow({ row, index }: { row: Holding; index: number }) {
  return (
    <tr>
      <th scope="row">{row.name}</th>
      <td>{row.code}</td>
      <td>{formatMoney(row.market_value_cny)}</td>
      <td className={pnlClass(row.unrealized_pnl_cny)}>{formatMoney(row.unrealized_pnl_cny, { signed: true })}</td>
      <td className={pnlClass(row.unrealized_pnl_pct)}>{formatPercent(row.unrealized_pnl_pct, { signed: true })}</td>
      <td>{formatUnitPrice(row.latest_price, row.asset_type)}</td>
      <td className="holding-unit-cost">{formatUnitPrice(row.average_cost, row.asset_type)}</td>
      <td className={pnlClass(row.today_pnl_cny)}>{formatMoney(row.today_pnl_cny, { signed: true })}</td>
      <td className={pnlClass(row.today_pnl_pct)}>{formatPercent(row.today_pnl_pct, { signed: true })}</td>
      <td>{formatPercent(row.position_pct)}</td>
      <td><Quantity value={row.shares} /></td>
      <td>{formatMoney(row.cost_value_cny)}</td>
      <td>{row.currency}</td>
      <td>{row.price_date ?? "—"}{row.quote_status === "indicative" ? "（参考价）" : ""}</td>
      <td>{assetTypes[row.asset_type]}</td>
      <td>{row.asset_type === "MUTUAL_FUND" ? row.fund_category : row.industry}</td>
      <td>{index + 1}</td>
    </tr>
  );
}

function HoldingsGroup({ market, title, rows }: { market: string; title: string; rows: Holding[] }) {
  const header = useRef<HTMLDivElement>(null);
  const titleId = `holding-group-${market}`;
  return (
    <Card className="holdings-group">
      <div className="section-heading"><h2 id={titleId}>{title}</h2><Badge>{rows.length} 项</Badge></div>
      {rows.length ? (
        <>
          <div className="holding-fixed-header" ref={header} aria-hidden="true">
            <table style={{ width: tableWidth }}><Columns /><Header /></table>
          </div>
          <div tabIndex={0} role="region" aria-labelledby={titleId} className="holding-scroll"
            onScroll={(event) => { if (header.current) header.current.scrollLeft = event.currentTarget.scrollLeft; }}>
            <table aria-labelledby={titleId} style={{ width: tableWidth }}>
              <Columns />
              <Header />
              <tbody>{rows.map((row, i) => <HoldingRow key={row.id} row={row} index={i} />)}</tbody>
            </table>
          </div>
        </>
      ) : <p className="muted-copy">暂无持仓</p>}
    </Card>
  );
}

export function HoldingsTable({ holdings }: { holdings: Holding[] }) {
  const [sort, setSort] = useState<SortKey>("market_value_cny");
  return (
    <>
      <div className="holdings-controls">
        <span>共 {holdings.length} 项资产</span>
        <label>各组排序 <select className="period-select" value={sort}
          onChange={(event) => setSort(event.target.value as SortKey)}>
          {sortOptions.map(([label, key]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
      </div>
      {groups.map(({ market, title }) => (
        <HoldingsGroup key={market} market={market} title={title}
          rows={holdings.filter((row) => row.market === market).sort((a, b) => {
            const first = toNumber(a[sort]), second = toNumber(b[sort]);
            if (first === null || second === null) return first === second ? 0 : first === null ? 1 : -1;
            return second - first;
          })} />
      ))}
    </>
  );
}
