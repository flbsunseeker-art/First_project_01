const metrics = [
  { label: "目标架构", value: "Next.js + FastAPI", tone: "blue" },
  { label: "数据策略", value: "SQLite first", tone: "cyan" },
  { label: "产品阶段", value: "MVP 重构", tone: "rose" },
];

const milestones = [
  "FastAPI health check",
  "Next.js responsive shell",
  "API client baseline",
  "Migrate ledger services",
];

export default function Home() {
  return (
    <main className="shell">
      <section className="hero-card">
        <div className="eyebrow">StockPilot</div>
        <div className="hero-grid">
          <div>
            <h1>多市场股票收益驾驶舱</h1>
            <p>
              本地优先的 A 股 / 港股 / 美股持仓总账。当前 milestone 正在搭建
              Web + API 的长期产品底座。
            </p>
          </div>
          <div className="status-pill">M1 Platform Scaffold</div>
        </div>
      </section>

      <section className="metric-grid" aria-label="architecture status">
        {metrics.map((metric) => (
          <article className={`metric-card metric-card-${metric.tone}`} key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </article>
        ))}
      </section>

      <section className="panel-grid">
        <article className="panel">
          <h2>当前目标</h2>
          <p>
            先跑通 FastAPI 后端和 Next.js 前端，再把现有账本、估值、行情、
            报告能力迁移进新的分层架构。
          </p>
        </article>
        <article className="panel">
          <h2>下一步</h2>
          <ul>
            {milestones.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </section>
    </main>
  );
}
