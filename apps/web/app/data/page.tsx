import { AppShell } from "../../components/app-shell";
import { BackupButton, CsvImportBox, ReportLink } from "../../components/data-actions";
import { Badge, Card } from "../../components/ui";
import { apiGet } from "../../lib/api";

export const dynamic = "force-dynamic";

type DataStatus = {
  status: string;
  schema_version?: string | null;
  database?: string;
  latest_snapshot?: {
    snapshot_date?: string;
    status?: string;
    error_message?: string | null;
    calculated_at?: string;
  } | null;
  latest_sync?: {
    started_at?: string;
    finished_at?: string | null;
    status?: string;
    details?: string | null;
  } | null;
};

async function loadDataStatus() {
  try {
    return await apiGet<DataStatus>("/api/v1/data/status");
  } catch {
    return {
      status: "unavailable",
      schema_version: null,
      database: "等待 FastAPI",
      latest_snapshot: null,
      latest_sync: null,
    } satisfies DataStatus;
  }
}

export default async function DataPage() {
  const dataStatus = await loadDataStatus();

  return (
    <AppShell>
      <main className="dashboard">
        <section className="page-heading">
          <Badge tone="info">Data</Badge>
          <h2>设置与数据</h2>
          <p>本地数据库状态、备份、报告和交易 CSV 导入导出集中在这里。</p>
        </section>

        <section className="panel-grid">
          <Card>
            <div className="section-heading">
              <h2>数据状态</h2>
              <Badge tone={dataStatus.status === "ok" ? "info" : "warning"}>
                {dataStatus.status}
              </Badge>
            </div>
            <div className="allocation-list">
              <span>Schema v{dataStatus.schema_version ?? "未知"}</span>
              <span>数据库：{dataStatus.database ?? "未知"}</span>
              <span>
                最新快照：
                {dataStatus.latest_snapshot?.snapshot_date ?? "暂无"} ·{" "}
                {dataStatus.latest_snapshot?.status ?? "无状态"}
              </span>
              <span>
                最近同步：
                {dataStatus.latest_sync?.started_at ?? "暂无"} ·{" "}
                {dataStatus.latest_sync?.status ?? "无状态"}
              </span>
            </div>
          </Card>

          <Card className="side-panel">
            <div className="section-heading">
              <h2>本地操作</h2>
              <Badge tone="warning">Manual</Badge>
            </div>
            <BackupButton />
            <ReportLink />
          </Card>
        </section>

        <Card>
          <div className="section-heading">
            <h2>交易 CSV 导入</h2>
            <Badge>Import</Badge>
          </div>
          <CsvImportBox />
        </Card>
      </main>
    </AppShell>
  );
}
