export type Overview = {
  status: string;
  total_market_value_cny?: string | null;
  total_cost_cny?: string | null;
  total_pnl_cny?: string | null;
  total_pnl_pct?: string | null;
  today_pnl_cny?: string | null;
  today_pnl_pct?: string | null;
  realized_pnl_cny?: string | null;
  unrealized_pnl_cny?: string | null;
  missing?: string[];
  updated_at?: string;
  latest_snapshot?: { snapshot_date?: string; status?: string } | null;
};

export type Holding = {
  id: number;
  market: string;
  code: string;
  name: string;
  industry: string;
  shares: string;
  average_cost: string;
  latest_price: string | null;
  change_pct?: string | null;
  currency: "CNY" | "HKD" | "USD";
  market_value_cny: string;
  cost_value_cny: string;
  unrealized_pnl_cny: string;
  unrealized_pnl_pct?: string | null;
  today_pnl_cny?: string | null;
  today_pnl_pct?: string | null;
  position_pct?: string | null;
};

export type Allocation = {
  industry?: string;
  market?: string;
  market_value_cny: string;
  position_pct: string;
};

export type HoldingsSummary = {
  holdings: Holding[];
  industry: Allocation[];
  market: Allocation[];
};

export type Trade = {
  id: number;
  market: string;
  code: string;
  name: string;
  trade_date: string;
  side: "BUY" | "SELL";
  shares: string;
  price: string;
  reason_category?: string;
  note?: string;
};

export type Security = {
  id: number;
  market: "A" | "HK" | "US";
  code: string;
  name: string;
  currency: "CNY" | "HKD" | "USD";
  industry: string;
};

export type DailyReturn = {
  snapshot_date: string;
  total_market_value_cny: string;
  cumulative_pnl_cny: string;
  daily_pnl_cny: string | null;
  status: string;
};
