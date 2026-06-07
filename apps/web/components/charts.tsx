"use client";

import { useState } from "react";

import { formatMoney, formatPercent, pnlClass, toNumber } from "../lib/format";
import type { Allocation, DailyReturn } from "../lib/types";

const TREND_TICK_STEP = 5000;

function formatWan(value: number) {
  const wan = value / 10000;
  return `${Number.isInteger(wan) ? wan.toFixed(0) : wan.toFixed(1)}万`;
}

export function TrendLineChart({ rows }: Readonly<{ rows: DailyReturn[] }>) {
  const points = rows
    .map((row) => ({
      date: row.snapshot_date,
      value: toNumber(row.total_market_value_cny),
    }))
    .filter((row): row is { date: string; value: number } => row.value !== null);

  if (points.length < 2) {
    return <div className="chart-empty">暂无足够趋势数据</div>;
  }

  const width = 640;
  const height = 300;
  const padding = { top: 24, right: 24, bottom: 38, left: 86 };
  const values = points.map((point) => point.value);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const min = Math.floor(rawMin / TREND_TICK_STEP) * TREND_TICK_STEP;
  const max = Math.ceil(rawMax / TREND_TICK_STEP) * TREND_TICK_STEP;
  const spread = max - min || TREND_TICK_STEP;
  const ticks = Array.from(
    { length: Math.floor(spread / TREND_TICK_STEP) + 1 },
    (_, index) => max - TREND_TICK_STEP * index,
  );
  const plotted = points.map((point, index) => ({
    ...point,
    x: padding.left + (index / (points.length - 1)) * (width - padding.left - padding.right),
    y: height - padding.bottom - ((point.value - min) / spread) * (height - padding.top - padding.bottom),
  }));
  const path = points
    .map((_, index) => {
      const point = plotted[index];
      return `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
    })
    .join(" ");
  const area = `${path} L ${width - padding.right} ${height - padding.bottom} L ${padding.left} ${height - padding.bottom} Z`;
  const latest = points[points.length - 1];
  const xLabels = [points[0], points[Math.floor(points.length / 2)], latest];

  return (
    <div className="trend-chart">
      <svg aria-label="总市值变化趋势" viewBox={`0 0 ${width} ${height}`} role="img">
        <defs>
          <linearGradient id="trendStroke" x1="0%" x2="100%" y1="0%" y2="0%">
            <stop offset="0%" stopColor="var(--accent-cyan)" />
            <stop offset="100%" stopColor="var(--accent-blue)" />
          </linearGradient>
          <linearGradient id="trendArea" x1="0%" x2="0%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(49, 230, 210, 0.32)" />
            <stop offset="100%" stopColor="rgba(49, 230, 210, 0)" />
          </linearGradient>
        </defs>
        {ticks.map((tick) => {
          const y = height - padding.bottom - ((tick - min) / spread) * (height - padding.top - padding.bottom);
          return (
            <g key={tick}>
              <path className="chart-grid" d={`M ${padding.left} ${y} H ${width - padding.right}`} />
              <text className="chart-axis-label" x={padding.left - 12} y={y + 4} textAnchor="end">
                {formatWan(tick)}
              </text>
            </g>
          );
        })}
        <path className="trend-area" d={area} />
        <path className="trend-path" d={path} />
        {plotted.map((point) => (
          <g className="trend-point" key={point.date}>
            <circle cx={point.x} cy={point.y} r="10">
              <title>{`${point.date}：${formatMoney(point.value)} CNY`}</title>
            </circle>
            <circle cx={point.x} cy={point.y} r="3.8" />
          </g>
        ))}
        {xLabels.map((point) => {
          const index = points.findIndex((item) => item.date === point.date);
          const x = padding.left + (index / (points.length - 1)) * (width - padding.left - padding.right);
          return (
            <text className="chart-axis-label" key={point.date} x={x} y={height - 12} textAnchor="middle">
              {point.date.slice(5)}
            </text>
          );
        })}
      </svg>
      <div className="trend-chart-meta">
        <span>{points[0].date}</span>
        <strong>{formatMoney(latest.value)}</strong>
        <span>{latest.date}</span>
      </div>
    </div>
  );
}

export function AllocationPie({
  items,
  labelKey,
}: Readonly<{ items: Allocation[]; labelKey: "industry" | "market" }>) {
  const [activeIndex, setActiveIndex] = useState(0);
  const segments = items
    .map((item) => ({
      label: item[labelKey] ?? "其他",
      value: toNumber(item.market_value_cny) ?? 0,
      pct: toNumber(item.position_pct) ?? 0,
    }))
    .filter((item) => item.value > 0);

  if (!segments.length) {
    return <div className="chart-empty">暂无分布数据</div>;
  }

  const colors = ["#31e6d2", "#56b6ff", "#ff5f57", "#f7c948", "#9ddcff", "#22c878"];
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  const active = segments[activeIndex] ?? segments[0];
  let cursor = 0;
  const chartSegments = segments.map((segment, index) => {
    const offset = cursor;
    cursor += segment.pct;
    return { ...segment, color: colors[index % colors.length], offset };
  });

  return (
    <div className="allocation-donut">
      <div className="donut-visual">
        <svg aria-label="分布环形图" className="donut-svg" viewBox="0 0 100 100">
          {chartSegments.map((segment, index) => (
            <circle
              aria-label={`${segment.label} ${formatMoney(segment.value)} ${formatPercent(segment.pct)}`}
              className={index === activeIndex ? "active" : ""}
              cx="50"
              cy="50"
              fill="none"
              key={segment.label}
              onClick={() => setActiveIndex(index)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  setActiveIndex(index);
                }
              }}
              pathLength="100"
              r="34"
              role="button"
              stroke={segment.color}
              strokeDasharray={`${segment.pct} ${100 - segment.pct}`}
              strokeDashoffset={-segment.offset}
              tabIndex={0}
              transform="rotate(-90 50 50)"
            />
          ))}
        </svg>
        <div className="donut-center">
          <span>{active.label}</span>
          <strong>{formatMoney(active.value)}</strong>
          <small>{formatPercent(active.pct)}</small>
        </div>
      </div>
      <div className="donut-legend">
        {segments.map((segment, index) => (
          <button
            aria-pressed={index === activeIndex}
            className={index === activeIndex ? "active" : ""}
            key={segment.label}
            onClick={() => setActiveIndex(index)}
            type="button"
          >
            <i style={{ background: colors[index % colors.length] }} />
            <span>{index + 1}</span>
            <strong>{segment.label}</strong>
            <b>{formatMoney(segment.value)}</b>
            <em>{formatPercent(segment.pct)}</em>
          </button>
        ))}
      </div>
    </div>
  );
}

export function TrendDetailList({ rows }: Readonly<{ rows: DailyReturn[] }>) {
  return (
    <div className="trend-detail-list">
      {rows.map((row) => (
        <div key={row.snapshot_date}>
          <span>{row.snapshot_date}</span>
          <strong>{formatMoney(row.total_market_value_cny)}</strong>
          <b className={pnlClass(row.daily_pnl_cny)}>
            {formatMoney(row.daily_pnl_cny, { signed: true })}
          </b>
        </div>
      ))}
    </div>
  );
}
