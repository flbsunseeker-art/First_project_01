import type { ReactNode } from "react";

const navItems = [
  { label: "总览", href: "/" },
  { label: "持仓", href: "/holdings" },
  { label: "交易", href: "/trades" },
  { label: "收益", href: "/analytics" },
  { label: "数据", href: "/data" },
];

export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-mark">SP</div>
        <nav>
          {navItems.map((item, index) => (
            <a className={index === 0 ? "active" : ""} href={item.href} key={item.href}>
              {item.label}
            </a>
          ))}
        </nav>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <span className="kicker">StockPilot</span>
            <h1>多市场股票收益驾驶舱</h1>
          </div>
          <div className="sync-chip">Local first</div>
        </header>
        {children}
      </div>

      <nav className="mobile-tabs" aria-label="移动端导航">
        {navItems.slice(0, 4).map((item, index) => (
          <a className={index === 0 ? "active" : ""} href={item.href} key={item.href}>
            {item.label}
          </a>
        ))}
      </nav>
    </div>
  );
}
