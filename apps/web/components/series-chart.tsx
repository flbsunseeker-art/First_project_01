"use client";

import { useEffect, useRef, useState } from "react";
import { formatAxisNumber, formatMoney, formatPercent, pnlClass } from "../lib/format";

export type ChartPoint = {
  label: string;
  date?: string;
  detail?: string;
  values: (number | null)[];
};
export type ChartSeries = { label: string; color: string };

export function SeriesChart({
  points, series, unit = "cny", bars = false, label, markerDate,
}: {
  points: ChartPoint[];
  series: ChartSeries[];
  unit?: "cny" | "percent";
  bars?: boolean;
  label: string;
  markerDate?: string | null;
}) {
  const canvas = useRef<HTMLDivElement>(null);
  const [[width, height], setSize] = useState([900, 308]);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize([entry.contentRect.width, entry.contentRect.height]);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const values = points.flatMap((point) => point.values.filter((value): value is number => value !== null));
  if (values.length === 0) return <div className="chart-empty">暂无可绘制数据</div>;

  const includeZero = bars || unit === "percent";
  const rawMin = Math.min(...values, ...(includeZero ? [0] : []));
  const rawMax = Math.max(...values, ...(includeZero ? [0] : []));
  const rough = (rawMax - rawMin || Math.max(Math.abs(rawMax) / 10, 1)) / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = ([1, 2, 2.5, 5, 10].find((size) => size * power >= rough) ?? 10) * power;
  const min = Math.floor(rawMin / step) * step;
  const max = Math.max(Math.ceil(rawMax / step) * step, min + step);
  const ticks = Array.from({ length: Math.round((max - min) / step) + 1 }, (_, index) =>
    (min + index * step) / step < 1e-9 && (min + index * step) / step > -1e-9
      ? 0 : min + index * step);
  const left = unit === "percent" ? 55 : 61;
  const right = width - 24;
  const top = 16;
  const bottom = height - 32;
  const plotWidth = Math.max(right - left, 1);
  const y = (value: number) => bottom - ((value - min) / (max - min)) * (bottom - top);
  const start = points[0].date ? Date.parse(points[0].date) : 0;
  const end = points.at(-1)?.date ? Date.parse(points.at(-1)!.date!) : start;
  const xs = points.map((point, index) => {
    if (bars) return left + (index + 0.5) * plotWidth / points.length;
    if (points.length === 1) return left + plotWidth / 2;
    const ratio = point.date && end > start
      ? (Date.parse(point.date) - start) / (end - start)
      : index / (points.length - 1);
    return left + ratio * plotWidth;
  });
  const labelIndices = new Set(
    Array.from({ length: Math.min(points.length, width < 480 ? 4 : 6) }, (_, i) => {
      const count = Math.min(points.length, width < 480 ? 4 : 6);
      return count <= 1 ? 0 : Math.round(i * (points.length - 1) / (count - 1));
    }),
  );
  const markerIndex = markerDate ? points.findIndex((point) => point.date === markerDate) : -1;
  const index = selected === null ? null : Math.min(selected, points.length - 1);
  const active = index === null ? null : points[index];
  const chosenX = index === null ? left : xs[index];
  const money = (value: number) => formatMoney(value, { signed: bars });
  const display = unit === "percent" ? (value: number) => formatPercent(value, { signed: true }) : money;
  const axis = (value: number) => {
    if (unit === "percent") return `${formatAxisNumber(value)}%`;
    if (Math.abs(value) >= 10_000) return `${formatAxisNumber(value / 10_000)}万`;
    return formatAxisNumber(value);
  };
  const barWidth = Math.max(2, Math.min(42, plotWidth / points.length * 0.62));

  return (
    <div className="series-chart" ref={canvas} tabIndex={0}
      aria-label={`${label}。使用左右方向键查看数据。`}
      onKeyDown={(event) => {
        if (event.key === "Escape") setSelected(null);
        if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
        event.preventDefault();
        const step = event.key === "ArrowLeft" ? -1 : 1;
        setSelected((at) => at === null ? points.length - 1
          : Math.min(points.length - 1, Math.max(0, at + step)));
      }}
      onBlur={() => setSelected(null)}
      onPointerLeave={(event) => { if (event.pointerType === "mouse") setSelected(null); }}
      onPointerMove={(event) => {
        if (event.pointerType === "touch" && event.buttons === 0) return;
        const offset = event.clientX - event.currentTarget.getBoundingClientRect().left;
        setSelected(xs.reduce((best, x, i) =>
          Math.abs(x - offset) < Math.abs(xs[best] - offset) ? i : best, 0));
      }}
      onPointerDown={(event) => {
        const offset = event.clientX - event.currentTarget.getBoundingClientRect().left;
        setSelected(xs.reduce((best, x, i) =>
          Math.abs(x - offset) < Math.abs(xs[best] - offset) ? i : best, 0));
      }}
    >
      <svg viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {ticks.map((tick) => (
          <g key={tick}>
            <line className={tick === 0 ? "series-zero" : "series-grid"} x1={left} x2={right} y1={y(tick)} y2={y(tick)} />
            <text className="series-axis" x={left - 8} y={y(tick) + 4} textAnchor="end">{axis(tick)}</text>
          </g>
        ))}
        {markerIndex >= 0 && (
          <line className="series-marker" x1={xs[markerIndex]} x2={xs[markerIndex]} y1={top} y2={bottom} />
        )}
        {bars ? points.map((point, i) => {
          const value = point.values[0];
          if (value === null) return null;
          return <rect key={i} x={xs[i] - barWidth / 2} width={barWidth}
            y={Math.min(y(value), y(0))} height={Math.max(2, Math.abs(y(value) - y(0)))}
            rx={2} fill={value > 0 ? "var(--profit-red)" : value < 0 ? "var(--loss-green)" : "var(--text-muted)"} />;
        }) : series.map((item, seriesIndex) => {
          let path = "";
          let connected = false;
          points.forEach((point, i) => {
            const value = point.values[seriesIndex];
            if (value === null || value === undefined) { connected = false; return; }
            path += `${connected ? "L" : "M"} ${xs[i]} ${y(value)} `;
            connected = true;
          });
          return <g key={item.label}>
            <path className="series-line" d={path} stroke={item.color} />
            {points.length === 1 && points[0].values[seriesIndex] !== null &&
              <circle cx={xs[0]} cy={y(points[0].values[seriesIndex]!)} r="4" fill={item.color} />}
          </g>;
        })}
        {[...labelIndices].map((i) => (
          <text key={i} className="series-axis" x={xs[i]} y={height - 10}
            textAnchor={bars || points.length === 1 ? "middle" : i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}>
            {points[i].label}
          </text>
        ))}
        {active && <line className="series-cursor" x1={chosenX} x2={chosenX} y1={top} y2={bottom} />}
      </svg>
      {active && (
        <div className="series-tooltip" role="status"
          style={{ left: Math.max(5, Math.min(chosenX + (chosenX > width / 2 ? -197 : 9), width - 198)) }}>
          <span>{active.date ?? active.label}</span>
          {series.map((item, i) => {
            const value = active.values[i];
            return <div key={item.label}>
              {item.label}
              <strong className={unit === "percent" ? pnlClass(value) : undefined}>
                {value == null ? "—" : display(value)}
              </strong>
            </div>;
          })}
          {active.detail && <small>{active.detail}</small>}
        </div>
      )}
    </div>
  );
}
