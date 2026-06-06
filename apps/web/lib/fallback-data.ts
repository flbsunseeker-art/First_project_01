import type { DailyReturn, Holding, Overview, Trade } from "./types";

export const fallbackOverview: Overview = {
  status: "offline-preview",
  total_market_value_cny: "0",
  total_cost_cny: "0",
  total_pnl_cny: "0",
  today_pnl_cny: null,
  realized_pnl_cny: "0",
  unrealized_pnl_cny: "0",
  missing: [],
  updated_at: "API 未连接",
};

export const fallbackHoldings: Holding[] = [];

export const fallbackTrades: Trade[] = [];

export const fallbackDailyReturns: DailyReturn[] = [];
