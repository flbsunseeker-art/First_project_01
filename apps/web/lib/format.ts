import type { Security } from "./types";

export type MoneyLike = number | string | null | undefined;

const axisNumber = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

export function toNumber(value: MoneyLike): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatMoney(
  value: MoneyLike,
  { signed = false, fractionDigits = 2 }: { signed?: boolean; fractionDigits?: number } = {},
) {
  const numeric = toNumber(value);
  if (numeric === null) {
    return "—";
  }
  const formatted = new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(Math.abs(numeric));
  const sign = signed ? (numeric >= 0 ? "+" : "-") : numeric < 0 ? "-" : "";
  return `${sign}${formatted}`;
}

export function formatPercent(value: MoneyLike, options: { signed?: boolean } = {}) {
  const numeric = toNumber(value);
  if (numeric === null) {
    return "—";
  }
  const sign = options.signed ? (numeric >= 0 ? "+" : "") : "";
  return `${sign}${numeric.toFixed(2)}%`;
}

export function formatUnitPrice(value: MoneyLike, assetType: Security["asset_type"]) {
  const precision = { STOCK: 2, ETF: 3, MUTUAL_FUND: 4 };
  return formatMoney(value, { fractionDigits: precision[assetType] });
}

export function formatAxisNumber(value: number) {
  return axisNumber.format(value);
}

export function pnlClass(value: MoneyLike) {
  const numeric = toNumber(value);
  if (numeric === null || numeric === 0) {
    return "value-neutral";
  }
  return numeric > 0 ? "value-profit" : "value-loss";
}
