"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navItems = [
  { label: "总览", href: "/" },
  { label: "持仓", href: "/holdings" },
  { label: "收益", href: "/analytics" },
  { label: "交易", href: "/trades" },
  { label: "数据", href: "/data" },
];

export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();

  function isActive(href: string) {
    return href === "/" ? pathname === href : pathname.startsWith(href);
  }

  return (
    <div className="app-shell">
      <div className="workspace">
        <header className="topbar">
          <div className="nav-row">
            <Link className="brand-mark" href="/" aria-label="StockPilot 总览">
              SP
            </Link>
            <nav className="top-nav" aria-label="主导航">
              {navItems.map((item) => (
                <Link
                  aria-current={isActive(item.href) ? "page" : undefined}
                  className={isActive(item.href) ? "active" : ""}
                  href={item.href}
                  key={item.href}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <div className="sync-chip">Local first</div>
          </div>

        </header>
        {children}
      </div>
    </div>
  );
}
