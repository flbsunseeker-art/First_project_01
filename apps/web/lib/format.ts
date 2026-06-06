export type MoneyLike = number | string | null | undefined;

export function toNumber(value: MoneyLike): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatMoney(value: MoneyLike, options: { signed?: boolean } = {}) {
  const numeric = toNumber(value);
  if (numeric === null) {
    return "-";
  }
  const formatted = new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(numeric));
  const sign = options.signed ? (numeric >= 0 ? "+" : "-") : numeric < 0 ? "-" : "";
  return `${sign}${formatted}`;
}

export function formatPercent(value: MoneyLike, options: { signed?: boolean } = {}) {
  const numeric = toNumber(value);
  if (numeric === null) {
    return "-";
  }
  const sign = options.signed ? (numeric >= 0 ? "+" : "") : "";
  return `${sign}${numeric.toFixed(2)}%`;
}

export function pnlClass(value: MoneyLike) {
  const numeric = toNumber(value);
  if (numeric === null || numeric === 0) {
    return "value-neutral";
  }
  return numeric > 0 ? "value-profit" : "value-loss";
}
