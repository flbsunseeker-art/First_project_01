"use client";

import { useState } from "react";
import type { CalendarHistory } from "../lib/types";
import { formatMoney, pnlClass, toNumber } from "../lib/format";
import { SeriesChart } from "./series-chart";

type Grain = "day" | "week" | "month" | "year";
const grains: { id: Grain; label: string }[] = [
  { id: "day", label: "按日" }, { id: "week", label: "按周" },
  { id: "month", label: "按月" }, { id: "year", label: "按年" },
];
const weekdayLabels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

const dayLabel = (day: string) => day.slice(5).replace("-", "/");

function dayRange(month: string) {
  const [year, m] = month.split("-").map(Number);
  return Array.from({ length: new Date(Date.UTC(year, m, 0)).getUTCDate() },
    (_, index) => `${month}-${String(index + 1).padStart(2, "0")}`);
}

function adjacentMonth(month: string, offset: number) {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m + offset - 1, 1)).toISOString().slice(0, 7);
}

export function ReturnCalendar({ history, initialMonth }: { history: CalendarHistory; initialMonth?: string }) {
  const [grain, setGrain] = useState<Grain>("day");
  const [view, setView] = useState<"grid" | "bars">("grid");
  const currentYear = history.as_of.slice(0, 4);
  const currentMonth = history.as_of.slice(0, 7);
  const firstMonth = history.days[0]?.date.slice(0, 7) ?? currentMonth;
  const [month, setMonth] = useState(
    initialMonth && /^\d{4}-(0[1-9]|1[0-2])$/.test(initialMonth)
      && initialMonth >= firstMonth && initialMonth <= currentMonth ? initialMonth : currentMonth,
  );
  const [year, setYear] = useState(currentYear);
  const years = history.calendar.years.map((item) => item.start.slice(0, 4));
  const days = new Map(history.days.map((day) => [day.date, day]));
  const calendarDays = dayRange(month);
  const offset = (new Date(`${month}-01T00:00:00Z`).getUTCDay() + 6) % 7;
  const daily = calendarDays.map((date) => ({
    start: date, end: date, pnl: days.get(date)?.pnl ?? null,
    label: date.slice(8).replace(/^0/, ""), note: days.get(date)?.status === "incomplete" ? "快照不完整" : "",
  }));
  const buckets = grain === "day" ? daily : (
    grain === "week" ? history.calendar.weeks[month] ?? [] :
    grain === "month" ? Object.values(history.calendar.months).filter((item) => item.start.startsWith(year)) :
    history.calendar.years
  ).map((item) => ({
    ...item,
    label: grain === "week" ? `${dayLabel(item.start)}–${dayLabel(item.end)}`
      : grain === "month" ? `${Number(item.start.slice(5, 7))} 月` : `${item.start.slice(0, 4)} 年`,
    note: item.pnl !== null && item.from_date && item.through &&
      (grain === "year" || item.partial || item.end > history.as_of)
      ? `数据 ${item.from_date} 至 ${item.through}` : "",
  }));
  const selectedTotal = grain === "day" || grain === "week" ? history.calendar.months[month] :
    grain === "month" ? history.calendar.years.find((item) => item.start.startsWith(year)) : null;

  function chooseMonth(value: string) {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value) || value < firstMonth || value > currentMonth) return;
    setMonth(value);
    const url = new URL(window.location.href);
    url.searchParams.set("month", value);
    window.history.replaceState(null, "", url);
  }

  return (
    <div className="returns-workspace">
      <div className="analytics-controls">
        <div className="segmented-control" aria-label="收益时间粒度">
          {grains.map((choice) => <button type="button" key={choice.id}
            aria-pressed={grain === choice.id} onClick={() => setGrain(choice.id)}>{choice.label}</button>)}
        </div>
        <div className="segmented-control" aria-label="收益视图">
          <button type="button" aria-pressed={view === "grid"} onClick={() => setView("grid")}>
            {grain === "day" ? "日历" : "区间"}
          </button>
          <button type="button" aria-pressed={view === "bars"} onClick={() => setView("bars")}>柱形图</button>
        </div>
      </div>
      <div className="returns-heading">
        {(grain === "day" || grain === "week") ? (
          <div className="analytics-month">
            <button type="button" aria-label="上个月" disabled={month <= firstMonth}
              onClick={() => chooseMonth(adjacentMonth(month, -1))}>‹</button>
            <input aria-label="选择月份" type="month" value={month} min={firstMonth} max={currentMonth}
              onChange={(event) => chooseMonth(event.target.value)} />
            <button type="button" aria-label="下个月" disabled={month >= currentMonth}
              onClick={() => chooseMonth(adjacentMonth(month, 1))}>›</button>
          </div>
        ) : grain === "month" ? (
          <label>年份 <select className="period-select" value={year} onChange={(e) => setYear(e.target.value)}>
            {years.map((option) => <option key={option}>{option}</option>)}
          </select></label>
        ) : <span>各自然年收益</span>}
        {selectedTotal && <div className="return-total">
          <span>{grain === "month" ? "全年合计" : "当月合计"}</span>
          <strong className={pnlClass(selectedTotal.pnl)}>{formatMoney(selectedTotal.pnl, { signed: true })}</strong>
          {selectedTotal.through && <small>数据至 {selectedTotal.through}</small>}
        </div>}
      </div>

      {view === "bars" ? (
        <SeriesChart key={`${grain}-${month}-${year}`} bars label="收益柱形图"
          points={buckets.map((item) => ({
            label: item.label,
            date: item.start === item.end ? item.start : `${item.start} 至 ${item.end}`,
            values: [toNumber(item.pnl)], detail: item.note,
          }))}
          series={[{ label: "收益（元）", color: "var(--accent-cyan)" }]} />
      ) : grain === "day" ? (
        <>
          <div className="return-weekdays">{weekdayLabels.map((item) => <span key={item}>{item}</span>)}</div>
          <div className="return-days" aria-label="按日收益日历">
            {Array.from({ length: offset }, (_, index) => <div key={`blank-${index}`} aria-hidden="true" />)}
            {daily.map((item) => (
              <div className="return-cell" key={item.start} title={`${item.start} · ${item.note || formatMoney(item.pnl, { signed: true })}`}>
                <span>{item.label}</span>
                <strong className={pnlClass(item.pnl)}>{formatMoney(item.pnl, { signed: true })}</strong>
                {item.note && <small>{item.note}</small>}
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="return-periods">
          {buckets.map((item) => <div className="return-cell" key={item.start}>
            <span>{item.label}</span>
            <strong className={pnlClass(item.pnl)}>{formatMoney(item.pnl, { signed: true })}</strong>
            {item.note && <small>{item.note}</small>}
          </div>)}
        </div>
      )}
      <p className="chart-note">单位：人民币元。红色为盈利，绿色为亏损，「—」表示暂无可用收益。</p>
    </div>
  );
}
