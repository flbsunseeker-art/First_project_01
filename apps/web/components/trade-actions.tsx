"use client";

import { useState } from "react";

import { apiSend } from "../lib/api";
import { Button } from "./ui";

export function TradeForm() {
  const [status, setStatus] = useState("等待录入");

  async function submit(formData: FormData) {
    setStatus("提交中...");
    try {
      await apiSend("POST", "/api/v1/trades", {
        security_id: Number(formData.get("security_id")),
        trade_date: formData.get("trade_date"),
        side: formData.get("side"),
        shares: formData.get("shares"),
        price: formData.get("price"),
        reason_category: formData.get("reason_category"),
        note: formData.get("note"),
      });
      setStatus("交易已保存，刷新后可查看");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "提交失败");
    }
  }

  return (
    <form action={submit} className="trade-form">
      <input name="security_id" placeholder="证券 ID" required />
      <input name="trade_date" type="date" required />
      <select name="side" defaultValue="BUY">
        <option value="BUY">买入</option>
        <option value="SELL">卖出</option>
      </select>
      <input name="shares" placeholder="股数" required />
      <input name="price" placeholder="成交价" required />
      <input name="reason_category" placeholder="交易理由" />
      <input name="note" placeholder="备注" />
      <Button>保存交易</Button>
      <span>{status}</span>
    </form>
  );
}

export function DeleteTradeButton({ tradeId }: Readonly<{ tradeId: number }>) {
  const [status, setStatus] = useState("");

  async function remove() {
    setStatus("删除中...");
    try {
      await apiSend("DELETE", `/api/v1/trades/${tradeId}`);
      setStatus("已删除，刷新后生效");
    } catch {
      setStatus("删除失败");
    }
  }

  return (
    <button className="inline-action" onClick={remove} type="button">
      删除 {status}
    </button>
  );
}
