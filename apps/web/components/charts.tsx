"use client";

import { useState, type CSSProperties } from "react";

import { formatMoney, formatPercent, pnlClass, toNumber } from "../lib/format";
import type { Allocation, DailyReturn } from "../lib/types";

const TREND_TICK_STEP = 10000;

type PlotPoint = {
  x: number;
  y: number;
};

function formatWan(value: number) {
  const wan = value / 10000;
  return `${Number.isInteger(wan) ? wan.toFixed(0) : wan.toFixed(1)}万`;
}

function createSmoothPath(points: PlotPoint[]) {
  if (points.length < 2) {
    return "";
  }

  const smoothing = 0.18;

  return points.reduce((path, point, index) => {
    if (index === 0) {
      return `M ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
    }

    const previous = points[index - 1];
    const beforePrevious = points[index - 2] ?? previous;
    const next = points[index + 1] ?? point;

    const controlStart = {
      x: previous.x + (point.x - beforePrevious.x) * smoothing,
      y: previous.y + (point.y - beforePrevious.y) * smoothing,
    };
    const controlEnd = {
      x: point.x - (next.x - previous.x) * smoothing,
      y: point.y - (next.y - previous.y) * smoothing,
    };

    return `${path} C ${controlStart.x.toFixed(2)} ${controlStart.y.toFixed(2)}, ${controlEnd.x.toFixed(2)} ${controlEnd.y.toFixed(2)}, ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
  }, "");
}

export function TrendLineChart({ rows }: Readonly<{ rows: DailyReturn[] }>) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
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
  const path = createSmoothPath(plotted);
  const area = `${path} L ${width - padding.right} ${height - padding.bottom} L ${padding.left} ${height - padding.bottom} Z`;
  const latest = points[points.length - 1];
  const xLabels = [points[0], points[Math.floor(points.length / 2)], latest];
  const activePoint = activeIndex === null ? null : plotted[activeIndex];
  const tooltipStyle = activePoint
    ? ({
        "--tooltip-x": `${(activePoint.x / width) * 100}%`,
        "--tooltip-y": `${(activePoint.y / height) * 100}%`,
      } as CSSProperties)
    : undefined;
  const tooltipClassName =
    activePoint && activePoint.x < padding.left + 100
      ? "trend-tooltip align-left"
      : activePoint && activePoint.x > width - padding.right - 100
        ? "trend-tooltip align-right"
        : "trend-tooltip";

  return (
    <div className="trend-chart">
      <div className="trend-chart-figure" onMouseLeave={() => setActiveIndex(null)}>
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
          {plotted.map((point, index) => (
            <g className={index === activeIndex ? "trend-point active" : "trend-point"} key={point.date}>
              <circle cx={point.x} cy={point.y} r="10">
                <title>{`${point.date}：${formatMoney(point.value)} CNY`}</title>
              </circle>
              <circle cx={point.x} cy={point.y} r="3.8" />
            </g>
          ))}
          {plotted.map((point, index) => {
            const previous = plotted[index - 1];
            const next = plotted[index + 1];
            const x = previous ? (previous.x + point.x) / 2 : padding.left;
            const nextX = next ? (next.x + point.x) / 2 : width - padding.right;

            return (
              <rect
                aria-label={`${point.date} ${formatMoney(point.value)} CNY`}
                className="trend-hover-zone"
                fill="transparent"
                height={height - padding.top - padding.bottom}
                key={point.date}
                onBlur={() => setActiveIndex(null)}
                onFocus={() => setActiveIndex(index)}
                onMouseEnter={() => setActiveIndex(index)}
                role="button"
                tabIndex={0}
                width={nextX - x}
                x={x}
                y={padding.top}
              />
            );
          })}
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
        {activePoint ? (
          <div className={tooltipClassName} style={tooltipStyle}>
            <span>{activePoint.date}</span>
            <strong>{formatMoney(activePoint.value)} CNY</strong>
          </div>
        ) : null}
      </div>
      <div className="trend-chart-meta">
        <span>{points[0].date}</span>
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
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
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
  const preview = previewIndex === null ? active : (segments[previewIndex] ?? active);
  let cursor = 0;
  const chartSegments = segments.map((segment, index) => {
    const offset = cursor;
    cursor += segment.pct;
    return { ...segment, color: colors[index % colors.length], offset };
  });

  return (
    <div className="allocation-donut">
      <div className="donut-visual" onMouseLeave={() => setPreviewIndex(null)}>
        <svg aria-label="分布环形图" className="donut-svg" viewBox="0 0 100 100">
          {chartSegments.map((segment, index) => (
            <circle
              aria-label={`${segment.label} ${formatMoney(segment.value)} ${formatPercent(segment.pct)}`}
              className={index === activeIndex ? "active" : index === previewIndex ? "preview" : ""}
              cx="50"
              cy="50"
              fill="none"
              key={segment.label}
              onClick={() => setActiveIndex(index)}
              onFocus={() => setPreviewIndex(index)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  setActiveIndex(index);
                }
              }}
              onMouseEnter={() => setPreviewIndex(index)}
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
          <strong>{preview.label}</strong>
          <small>{formatMoney(preview.value)}</small>
          <small>{formatPercent(preview.pct)}</small>
        </div>
      </div>
      <div className="donut-legend" onMouseLeave={() => setPreviewIndex(null)}>
        {segments.map((segment, index) => (
          <button
            aria-pressed={index === activeIndex}
            className={index === activeIndex ? "active" : index === previewIndex ? "preview" : ""}
            key={segment.label}
            onClick={() => setActiveIndex(index)}
            onFocus={() => setPreviewIndex(index)}
            onMouseEnter={() => setPreviewIndex(index)}
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
