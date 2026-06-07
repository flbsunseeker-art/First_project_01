"use client";

import { useMemo, useState } from "react";

import { formatMoney, formatPercent, pnlClass, toNumber } from "../lib/format";
import type { Holding } from "../lib/types";

const marketRank: Record<string, number> = { A: 1, HK: 2, US: 3 };
const marketLabel: Record<string, string> = { A: "A 股", HK: "港股", US: "美股" };

const sortOptions = [
  { label: "默认市场归类", value: "market_group" },
  { label: "按市值排序", value: "market_value_cny" },
  { label: "按累计收益金额排序", value: "unrealized_pnl_cny" },
  { label: "按累计收益率排序", value: "unrealized_pnl_pct" },
  { label: "按今日收益排序", value: "today_pnl_cny" },
  { label: "按仓位占比排序", value: "position_pct" },
] as const;

type SortKey = (typeof sortOptions)[number]["value"];

export function HoldingsTable({ holdings }: Readonly<{ holdings: Holding[] }>) {
  const [sortKey, setSortKey] = useState<SortKey>("market_group");
  const sorted = useMemo(() => {
    return [...holdings].sort((a, b) => {
      if (sortKey === "market_group") {
        const marketDelta = (marketRank[a.market] ?? 9) - (marketRank[b.market] ?? 9);
        if (marketDelta !== 0) {
          return marketDelta;
        }
        return (toNumber(b.market_value_cny) ?? Number.NEGATIVE_INFINITY) -
          (toNumber(a.market_value_cny) ?? Number.NEGATIVE_INFINITY);
      }
      return (toNumber(b[sortKey]) ?? Number.NEGATIVE_INFINITY) -
        (toNumber(a[sortKey]) ?? Number.NEGATIVE_INFINITY);
    });
  }, [holdings, sortKey]);

  return (
    <div className="holdings-table-card">
      <div className="table-toolbar">
        <span>共 {holdings.length} 只股票</span>
        <label>
          <span>排序</span>
          <select
            onChange={(event) => setSortKey(event.target.value as SortKey)}
            value={sortKey}
          >
            {sortOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="table-frame holdings-table-frame">
        <table>
          <thead>
            <tr>
              {[
                "#",
                "所属市场",
                "股票名称",
                "股票代码",
                "所属行业",
                "成本价格",
                "最新价格",
                "币种",
                "持仓股数",
                "持仓成本 CNY",
                "最新市值 CNY",
                "累计收益 CNY",
                "累计收益率",
                "今日收益 CNY",
                "今日收益率",
                "仓位占比",
              ].map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, index) => (
              <tr key={`${row.market}-${row.code}`}>
                <td>{index + 1}</td>
                <td>{marketLabel[row.market] ?? row.market}</td>
                <td>{row.name}</td>
                <td>{row.code}</td>
                <td>{row.industry}</td>
                <td>{formatMoney(row.average_cost)}</td>
                <td>{formatMoney(row.latest_price)}</td>
                <td>{row.currency}</td>
                <td>{formatMoney(row.shares)}</td>
                <td>{formatMoney(row.cost_value_cny)}</td>
                <td>{formatMoney(row.market_value_cny)}</td>
                <td className={pnlClass(row.unrealized_pnl_cny)}>
                  {formatMoney(row.unrealized_pnl_cny, { signed: true })}
                </td>
                <td className={pnlClass(row.unrealized_pnl_pct)}>
                  {formatPercent(row.unrealized_pnl_pct, { signed: true })}
                </td>
                <td className={pnlClass(row.today_pnl_cny)}>
                  {formatMoney(row.today_pnl_cny, { signed: true })}
                </td>
                <td className={pnlClass(row.today_pnl_pct)}>
                  {formatPercent(row.today_pnl_pct, { signed: true })}
                </td>
                <td>{formatPercent(row.position_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
