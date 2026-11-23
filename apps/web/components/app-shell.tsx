"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useTransition, type ReactNode } from "react";

const navItems = [
  { label: "持仓总览", shortLabel: "总览", href: "/", icon: "M3 3v18h18M7 16l4-5 4 2 5-6" },
  { label: "持仓明细", shortLabel: "持仓", href: "/holdings", icon: "M3 4h18v16H3zM3 9h18M3 14h18M10 9v11" },
  { label: "诊断建议", shortLabel: "诊断", href: "/research", icon: "M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15ZM16 16l5 5M6 11h2l2-3 2 5 2-2" },
  { label: "交易流水", shortLabel: "流水", href: "/trades", icon: "M3 7h17m-4-4 4 4-4 4M21 17H4m4-4-4 4 4 4" },
];

export function LoadingPanel({ label = "正在读取数据…" }: { label?: string }) {
  return <div className="card page-loading" role="status"><span />{label}</div>;
}

export function PageLoading({ pathname }: { pathname: string }) {
  return (
    <main className="dashboard">
      <header className="page-heading"><h1>{navItems.find((item) => item.href === pathname)?.label ?? "StockPilot"}</h1></header>
      <LoadingPanel />
    </main>
  );
}

export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();
  const [requested, setRequested] = useState<string | null>(null);
  const [pending, startNavigation] = useTransition();
  const waitingForRoute = pending && requested !== null && requested !== pathname;
  const activePath = waitingForRoute ? requested : pathname;

  function navigate(href: string, event: { preventDefault(): void }) {
    if (href === pathname && !pending) return;
    event.preventDefault();
    setRequested(href);
    startNavigation(() => router.push(href));
  }

  return (
    <div className="app-shell">
      <header className="workspace-header">
        <span className="brand-mark" aria-hidden="true">SP</span>
        <div className="workspace-brand">
          <strong>Stock<span className="brand-name-accent">Pilot</span></strong>
          <span className="brand-slogan" lang="en">See your portfolio across markets, understand what moves it, and chart your course.</span>
          <span className="brand-translation">看清跨市场持仓，读懂收益为何起伏，下一步心中有数。</span>
        </div>
      </header>
      <aside className="workspace-sidebar">
        <nav className="workspace-nav" aria-label="StockPilot 主导航">
          {navItems.map((item) => (
            <Link href={item.href} key={item.href} className="workspace-nav-link"
              aria-label={item.label} aria-current={activePath === item.href ? "page" : undefined}
              onNavigate={(event) => navigate(item.href, event)}>
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
                <path d={item.icon} />
              </svg>
              <span className="workspace-nav-compact" aria-hidden="true">{item.shortLabel}</span>
              <span className="workspace-nav-label" aria-hidden="true">{item.label}</span>
              {waitingForRoute && item.href === requested && <span className="nav-pending" aria-hidden="true" />}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="workspace">
        {waitingForRoute ? <PageLoading pathname={requested} /> : children}
      </div>
    </div>
  );
}
