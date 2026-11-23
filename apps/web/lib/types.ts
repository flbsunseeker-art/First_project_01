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
  snapshot_date?: string;
  valuation_date?: string;
  quote_from?: string | null;
  quote_through?: string | null;
  asset_values?: Record<"stocks" | "funds", string>;
  latest_snapshot?: { snapshot_date?: string; status?: string } | null;
};

export type MarketRefresh = {
  status: "idle" | "running" | "ok" | "partial" | "failed" | "offline";
  phase: "quotes" | "history" | null;
  finished_at: string | null;
  warnings: string[];
  overview: Overview | null;
};

export type Holding = {
  id: number;
  market: string;
  code: string;
  name: string;
  industry: string;
  asset_type: "STOCK" | "ETF" | "MUTUAL_FUND";
  fund_category?: string;
  shares: string;
  average_cost: string;
  latest_price: string | null;
  change_pct?: string | null;
  currency: "CNY" | "HKD" | "USD";
  market_value_cny: string | null;
  cost_value_cny: string | null;
  unrealized_pnl_cny: string | null;
  unrealized_pnl_pct?: string | null;
  today_pnl_cny?: string | null;
  today_pnl_pct?: string | null;
  position_pct?: string | null;
  price_date?: string | null;
  quote_status?: string;
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
  investment_plans: InvestmentPlan[];
  allocation_total_cny: string;
  market_sources: { label: string; as_of: string; url: string }[];
  unresolved_market: {
    market: string;
    code: string;
    name: string;
    market_value_cny: string;
    holding_pct: string;
    reason: string;
  }[];
  quote_from: string | null;
  quote_through: string | null;
  missing: string[];
  cached: boolean;
};

export type InvestmentPlan = {
  id: number;
  security_id: number;
  code: string;
  name: string;
  fund_category: string;
  amount_cny: string;
  start_date: string;
  active: number;
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
  currency: Security["currency"];
  asset_type: Security["asset_type"];
  reason_category?: string;
  note?: string;
};

export type Security = {
  id: number;
  market: "A" | "HK" | "US" | "FUND";
  asset_type: "STOCK" | "ETF" | "MUTUAL_FUND";
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

export type ReturnPeriod = "today" | "year" | "last_year" | "rolling_year";

export type PeriodPerformance = {
  pnl: string | null;
  return_pct: string | null;
  from_date: string | null;
  through: string | null;
  partial: boolean;
};

export type PerformanceHistory = {
  as_of: string;
  fund_coverage_from: string | null;
  periods: Record<ReturnPeriod, PeriodPerformance>;
  days: {
    date: string;
    market_value: string | null;
    pnl: string | null;
    status: "ok" | "incomplete";
  }[];
};

export type CalendarBucket = {
  start: string;
  end: string;
  pnl: string | null;
  from_date: string | null;
  through: string | null;
  partial: boolean;
};

export type CalendarHistory = PerformanceHistory & {
  calendar: {
    months: Record<string, CalendarBucket>;
    weeks: Record<string, CalendarBucket[]>;
    years: CalendarBucket[];
  };
};

export type BenchmarkComparison = {
  points: { date: string; portfolio: string; csi300: string; csi500: string }[];
  from_date: string | null;
  through: string | null;
  excess: Partial<Record<"csi300" | "csi500", string>>;
  partial?: boolean;
};
