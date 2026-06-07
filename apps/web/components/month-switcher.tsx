"use client";

import { useRouter } from "next/navigation";

export function MonthSwitcher({ month }: Readonly<{ month: string }>) {
  const router = useRouter();
  const [year, monthNumber] = month.split("-").map(Number);

  function shift(delta: number) {
    const target = new Date(year, monthNumber - 1 + delta, 1);
    return `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, "0")}`;
  }

  function go(target: string) {
    router.replace(`/analytics?month=${target}`);
  }

  return (
    <div className="month-switcher">
      <button aria-label="上月" onClick={() => go(shift(-1))} type="button">
        ‹
      </button>
      <input
        aria-label="选择月份"
        onChange={(event) => go(event.target.value)}
        type="month"
        value={month}
      />
      <button aria-label="下月" onClick={() => go(shift(1))} type="button">
        ›
      </button>
    </div>
  );
}
