import Link from "next/link";
import { Suspense } from "react";
import { LoadingPanel } from "../../components/app-shell";
import { LoadError } from "../../components/load-state";
import { Badge, Card, DataTable } from "../../components/ui";
import { apiGet } from "../../lib/api";
import { formatMoney, formatPercent, pnlClass } from "../../lib/format";
import "./research.css";

export const dynamic = "force-dynamic";

type Evidence = { title: string; url: string; published_on: string; note?: string; assets: string[] };
type Finding = {
  id: string;
  scope: string;
  title: string;
  fact: string;
  interpretation: string;
  holding_view?: string;
  selection_reason?: string;
  previous_review?: string;
  assets: string[];
  evidence: string[];
};
const strategyLabels = {
  "优先复核配置": "先查仓位",
  "带条件观察": "等验证条件出现",
  "维持": "维持仓位",
};
type Strategy = { finding: string; direction: keyof typeof strategyLabels; action_label?: string; action: string; checkpoint: string };
type Opportunity = { title: string; reasoning: string; check: string; evidence: string[] };
type Candidate = { title: string; reason: string; assets: string[]; evidence: string[] };
type Asset = {
  key: string;
  name: string;
  weight: string;
  market_value_cny: string;
  floating_pnl_cny: string;
  weekly_pnl_cny: string | null;
  price_date: string | null;
  signals: string[];
};
type Edition = { cutoff: string; number: number; published_at: string };
type Diagnosis = Edition & {
  snapshot: {
    cutoff: string;
    start: string;
    end: string;
    total_cny: string;
    floating_pnl_cny: string;
    weekly_pnl_cny: string | null;
    assets: Asset[];
    markets: { market: string; position_pct: string }[];
    stock_ranks: { gains: string[]; losses: string[] };
  };
  analysis: {
    summary: string;
    strategy_summary: string;
    outside_summary: string;
    key_changes?: string[];
    findings: Finding[];
    strategies: Strategy[];
    outside: Opportunity[];
    deferred?: Candidate[];
    evidence: Record<string, Evidence>;
  };
};
type Archive = { editions: Edition[]; report: Diagnosis | null };
type ResearchParams = Promise<{ cutoff?: string }>;

function Sources({ sources, showNotes = false }: { sources: Evidence[]; showNotes?: boolean }) {
  if (!sources.length) return null;
  return <ul className="diagnosis-sources">
    {sources.map((source) => <li key={source.url}>
      <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>
      <time dateTime={source.published_on}>{source.published_on}</time>
      {showNotes && source.note && <span className="diagnosis-source-note">{source.note}</span>}
    </li>)}
  </ul>;
}

function StockRanking({ title, keys, assets }: { title: string; keys: string[]; assets: Map<string, Asset> }) {
  return <section className="diagnosis-ranking" aria-label={title}>
    <h3>{title}</h3>
    {keys.length ? <DataTable
      columns={["股票", "持仓占比", "浮盈亏", "本周贡献"]}
      rows={keys.map((key) => assets.get(key)).filter((asset): asset is Asset => asset !== undefined).map((asset) => [
        <span className="rank-company" key={asset.key}>{asset.name}<small>{asset.key.replace(":", " · ")}</small></span>,
        formatPercent(asset.weight),
        <span className={pnlClass(asset.floating_pnl_cny)} key="floating">
          {formatMoney(asset.floating_pnl_cny, { signed: true })}
        </span>,
        <span className={pnlClass(asset.weekly_pnl_cny)} key="weekly">
          {formatMoney(asset.weekly_pnl_cny, { signed: true })}
        </span>,
      ])}
    /> : <p className="muted-copy">本周无符合条件的股票。</p>}
  </section>;
}

function CandidateReview({ items, evidence, title }: { items: Candidate[]; evidence: Record<string, Evidence>; title: string }) {
  if (!items.length) return null;
  return <details className="diagnosis-secondary">
    <summary>{title} · {items.length} 项</summary>
    <ul className="candidate-list">{items.map((item) => <li key={item.title}>
      <strong>{item.title}</strong><p>{item.reason}</p>
      <Sources sources={item.evidence.map((id) => evidence[id])} />
    </li>)}</ul>
  </details>;
}

function DiagnosisReport({ report, editions }: { report: Diagnosis; editions: Edition[] }) {
  const { snapshot, analysis } = report;
  const { findings, strategies, outside, evidence } = analysis;
  const assetsByKey = new Map(snapshot.assets.map((asset) => [asset.key, asset]));
  const checked = new Set(Object.values(evidence).flatMap((item) => item.assets));
  const deferred = analysis.deferred ?? [];
  const featured = new Set([...findings, ...deferred].flatMap((item) => item.evidence));
  const additional = Object.entries(evidence).filter(([id, item]) => item.assets.length && item.note && !featured.has(id));
  const delayed = snapshot.assets.filter((asset) => asset.price_date !== snapshot.end);
  const findingsByScope = [
    { title: "组合层面", items: findings.filter((item) => item.scope === "组合") },
    { title: "重点个股", items: findings.filter((item) => item.scope === "个股") },
  ];

  return <>
    <div className="diagnosis-meta">
      <div>
        <Badge>第 {report.number} 期</Badge>
        <span>{snapshot.start} 至 {snapshot.end}</span>
        <small>信息截止 {snapshot.cutoff.slice(0, 16).replace("T", " ")}（北京时间）</small>
      </div>
      {editions.length > 1 && <form action="/research" className="week-picker">
        <label>周报归档 <select name="cutoff" className="period-select" defaultValue={report.cutoff}>
          {editions.map((item) => <option key={item.cutoff} value={item.cutoff}>第 {item.number} 期 · {item.cutoff}</option>)}
        </select></label>
        <button type="submit" className="button button-ghost">查看</button>
      </form>}
    </div>

    <Card className="diagnosis-summary">
      <div className="section-heading"><h2>本周结论</h2></div>
      <dl className="diagnosis-metrics">
        <div><dt>本周盈亏 · CNY</dt><dd className={pnlClass(snapshot.weekly_pnl_cny)}>{formatMoney(snapshot.weekly_pnl_cny, { signed: true })}</dd></div>
        <div><dt>周末持仓市值 · CNY</dt><dd>{formatMoney(snapshot.total_cny)}</dd></div>
        <div><dt title="截至周末仍持有的资产，按市值减持仓成本计算">当前持仓盈亏 · CNY</dt><dd className={pnlClass(snapshot.floating_pnl_cny)}>{formatMoney(snapshot.floating_pnl_cny, { signed: true })}</dd></div>
        <div><dt>账本扫描</dt><dd>{snapshot.assets.length} 项持仓</dd></div>
      </dl>
      <div className="diagnosis-week-note">
        <h3>本周关键变化</h3>
        <p>{analysis.summary}</p>
        {!!analysis.key_changes?.length && <ul>
          {analysis.key_changes.map((change) => <li key={change}>{change}</li>)}
        </ul>}
      </div>
      <p className="diagnosis-rank-note">按周末股票浮盈亏金额排名，金额为人民币元。周贡献已剔除资金进出。</p>
      <div className="diagnosis-rankings">
        <StockRanking title="股票浮盈 Top 5" keys={snapshot.stock_ranks.gains} assets={assetsByKey} />
        <StockRanking title="股票浮亏 Top 5" keys={snapshot.stock_ranks.losses} assets={assetsByKey} />
      </div>
    </Card>

    <Card className="diagnosis-section" id="portfolio-diagnosis">
      <div className="section-heading"><h2>当前持仓分析与问题定位</h2></div>
      <div className="diagnosis-exposure">
        <a href="#scan-coverage">账本扫描 {snapshot.assets.length} 项 · 公开资料覆盖 {checked.size} 项</a>
        {snapshot.markets.map((market) => <span key={market.market}>
          {market.market} <b>{formatPercent(market.position_pct)}</b>
        </span>)}
      </div>
      {findingsByScope.filter(({ items }) => items.length).map(({ title, items }) => (
        <section className="diagnosis-group" key={title}>
          <h3>{title}</h3>
          {items.map((finding) => (
            <article className="diagnosis-item" id={`finding-${finding.id}`} key={finding.id}>
              <h4>{finding.title}</h4>
              {finding.holding_view && <p className="diagnosis-holding-view">{finding.holding_view}</p>}
              {finding.selection_reason && <p className="finding-context"><strong>本周入选</strong> {finding.selection_reason}</p>}
              {finding.previous_review && <p className="finding-context"><strong>上期回看</strong> {finding.previous_review}</p>}
              <p>{finding.fact}</p>
              <p className="diagnosis-interpretation">{finding.interpretation}</p>
              <div className="diagnosis-item-meta">
                {finding.assets.length > 0 && <span>{finding.assets.map((key) => assetsByKey.get(key)?.name ?? key).join("、")}</span>}
                <a href={`#strategy-${finding.id}`}>看对应建议</a>
              </div>
              <Sources sources={finding.evidence.map((id) => evidence[id])} />
            </article>
          ))}
        </section>
      ))}
      {!findings.length && <p className="muted-copy">本周暂无需要单列的持仓问题。</p>}
      <CandidateReview title="其他持仓的取舍依据" items={deferred.filter((item) => item.assets.length)} evidence={evidence} />
      {additional.length > 0 && <details className="diagnosis-secondary">
        <summary>其他已核实的持仓动态</summary>
        <Sources sources={additional.map(([, source]) => source)} showNotes />
      </details>}
    </Card>

    <Card className="diagnosis-section" id="portfolio-strategies">
      <div className="section-heading"><h2>后续调整建议</h2></div>
      <section className="diagnosis-group">
        <h3>现有持仓</h3>
        <p className="diagnosis-strategy-summary">{analysis.strategy_summary}</p>
        {strategies.map((strategy) => (
          <article className="diagnosis-item" id={`strategy-${strategy.finding}`} key={strategy.finding}>
            <div className="diagnosis-item-title">
              <Badge>
                {strategy.action_label || strategyLabels[strategy.direction]}
              </Badge>
              <h4><a href={`#finding-${strategy.finding}`}>{findings.find((item) => item.id === strategy.finding)?.title}</a></h4>
            </div>
            <p>{strategy.action}</p>
            <p className="diagnosis-interpretation"><strong>下一步关注</strong> {strategy.checkpoint}</p>
          </article>
        ))}
      </section>
      <section className="diagnosis-group" id="market-watch">
        <h3>持仓之外</h3>
        {outside.length ? outside.map((item) => <article className="diagnosis-item" key={item.title}>
          <h4>{item.title}</h4>
          <p>{item.reasoning}</p>
          <p className="diagnosis-interpretation"><strong>研究条件</strong> {item.check}</p>
          <Sources sources={item.evidence.map((id) => evidence[id])} />
        </article>) : <p className="muted-copy">{analysis.outside_summary || "本期暂无值得单列的方向。"}</p>}
        <CandidateReview title="本期比较过的其他方向" items={deferred.filter((item) => !item.assets.length)} evidence={evidence} />
      </section>
    </Card>

    <Card className="diagnosis-ledger">
      <details>
        <summary id="scan-coverage">本期扫描明细 · {snapshot.assets.length} 项持仓</summary>
        <p>账本估值截至 {snapshot.end}。本期另核对了 {checked.size} 项持仓的公开披露。</p>
        {delayed.length > 0 && <p>{delayed.length} 项持仓沿用最近可用的净值或行情，日期见明细。</p>}
        {snapshot.weekly_pnl_cny == null && <p>本周盈亏归因待补齐。</p>}
        <DataTable columns={["标的", "代码", "持仓占比", "当前浮盈亏 CNY", "本周盈亏贡献 CNY", "行情／净值日", "筛查信号", "披露核对"]}
          rows={snapshot.assets.map((asset) => [
            asset.name, asset.key.replace(":", " · "), formatPercent(asset.weight),
            <span key="float" className={pnlClass(asset.floating_pnl_cny)}>{formatMoney(asset.floating_pnl_cny, { signed: true })}</span>,
            <span key="week" className={pnlClass(asset.weekly_pnl_cny)}>{formatMoney(asset.weekly_pnl_cny, { signed: true })}</span>,
            asset.price_date ?? "—", asset.signals.join("、") || "—", checked.has(asset.key) ? "已核对" : "—",
          ])}
        />
        <Sources sources={Object.values(evidence)} showNotes />
      </details>
      <small>本期研判由 Codex 整理 · 发布于 {report.published_at.slice(0, 16).replace("T", " ")}</small>
    </Card>
  </>;
}

async function ResearchContent({ searchParams }: { searchParams: ResearchParams }) {
  const { cutoff } = await searchParams;
  const query = cutoff ? "?" + new URLSearchParams({ cutoff }) : "";
  const archive = await apiGet<Archive>("/api/v1/research/diagnosis" + query).catch(() => null);
  if (!archive) return <Card><LoadError message="周报暂时无法读取。" />{cutoff && <Link href="/research">查看最新周报</Link>}</Card>;
  if (!archive.report) return <Card><p>首期周报尚未发布。</p></Card>;
  return <DiagnosisReport report={archive.report} editions={archive.editions} />;
}

export default function ResearchPage({ searchParams }: { searchParams: ResearchParams }) {
  return <main className="dashboard weekly-review">
    <header className="page-heading"><h1>诊断建议</h1></header>
    <Suspense fallback={<LoadingPanel label="正在读取周报…" />}>
      <ResearchContent searchParams={searchParams} />
    </Suspense>
  </main>;
}
