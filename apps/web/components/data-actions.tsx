"use client";

import { useState } from "react";

import { apiSend, apiSendText } from "../lib/api";
import { Button } from "./ui";

export function BackupButton() {
  const [status, setStatus] = useState("");

  async function backup() {
    setStatus("备份中...");
    try {
      const result = await apiSend<{ path: string }>("POST", "/api/v1/data/backup");
      setStatus(`已备份：${result.path}`);
    } catch {
      setStatus("备份失败");
    }
  }

  return (
    <div className="action-row">
      <Button>数据库备份</Button>
      <button className="inline-action" onClick={backup} type="button">
        执行
      </button>
      <span>{status}</span>
    </div>
  );
}

export function ReportLink() {
  return (
    <div className="action-row">
      <a className="button button-ghost" href="http://127.0.0.1:8000/api/v1/report/html">
        打开 HTML 报告
      </a>
      <a className="button button-ghost" href="http://127.0.0.1:8000/api/v1/trades/export.csv">
        导出交易 CSV
      </a>
    </div>
  );
}

export function CsvImportBox() {
  const [content, setContent] = useState("");
  const [status, setStatus] = useState("");

  async function submit() {
    setStatus("导入中...");
    try {
      const result = await apiSendText<{ imported: number; errors: string[] }>(
        "POST",
        "/api/v1/trades/import.csv",
        content,
        "text/csv",
      );
      setStatus(`已导入 ${result.imported} 条，失败 ${result.errors.length} 条`);
    } catch {
      setStatus("导入失败");
    }
  }

  return (
    <div className="csv-import-box">
      <textarea
        onChange={(event) => setContent(event.target.value)}
        placeholder="粘贴交易 CSV 内容"
        value={content}
      />
      <button className="inline-action" onClick={submit} type="button">
        导入 CSV
      </button>
      <span>{status}</span>
    </div>
  );
}
