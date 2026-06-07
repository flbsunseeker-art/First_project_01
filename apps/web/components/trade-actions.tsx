"use client";

import { useState } from "react";

import { apiSend } from "../lib/api";
import type { Security } from "../lib/types";
import { Button } from "./ui";

const reasons = ["行业趋势判断", "个股基本面", "价格 / 估值判断", "仓位 / 情绪管理"];

export function TradeForm({ securities }: Readonly<{ securities: Security[] }>) {
  const [status, setStatus] = useState("等待录入");
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [market, setMarket] = useState<Security["market"]>("A");
  const currencyByMarket: Record<Security["market"], Security["currency"]> = {
    A: "CNY",
    HK: "HKD",
    US: "USD",
  };

  async function submit(formData: FormData) {
    setStatus("提交中...");
    const isExisting = formData.get("trade_target") === "existing";
    try {
      await apiSend("POST", "/api/v1/trades", {
        security_id: isExisting ? Number(formData.get("security_id")) : null,
        market: isExisting ? null : formData.get("market"),
        code: isExisting ? null : formData.get("code"),
        name: isExisting ? null : formData.get("name"),
        currency: isExisting ? null : formData.get("currency"),
        industry: isExisting ? "其他" : formData.get("industry"),
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
    <form action={submit} className="trade-form trade-entry-form">
      <div className="trade-target-toggle">
        <label>
          <input
            checked={mode === "existing"}
            name="trade_target"
            onChange={() => setMode("existing")}
            type="radio"
            value="existing"
          />
          已有股票
        </label>
        <label>
          <input
            checked={mode === "new"}
            name="trade_target"
            onChange={() => setMode("new")}
            type="radio"
            value="new"
          />
          新股票
        </label>
      </div>

      {mode === "existing" ? (
        <label className="form-field span-2">
          <span>已有股票</span>
          <select name="security_id" required>
            <option value="">选择当前股票</option>
            {securities.map((security) => (
              <option key={security.id} value={security.id}>
                {security.market} · {security.code} · {security.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <>
          <label className="form-field">
            <span>市场</span>
            <select
              name="market"
              onChange={(event) => setMarket(event.target.value as Security["market"])}
              value={market}
            >
              <option value="A">A 股</option>
              <option value="HK">港股</option>
              <option value="US">美股</option>
            </select>
          </label>
          <label className="form-field">
            <span>股票代码</span>
            <input name="code" placeholder="例如：AAPL" required />
          </label>
          <label className="form-field">
            <span>股票名称</span>
            <input name="name" placeholder="股票名称" required />
          </label>
          <label className="form-field">
            <span>币种</span>
            <input name="currency" readOnly value={currencyByMarket[market]} />
          </label>
          <label className="form-field">
            <span>所属行业</span>
            <input name="industry" placeholder="选择行业" required />
          </label>
        </>
      )}

      <label className="form-field">
        <span>交易日期</span>
        <input name="trade_date" type="date" required />
      </label>
      <label className="form-field">
        <span>方向</span>
        <select name="side" defaultValue="BUY">
          <option value="BUY">买入</option>
          <option value="SELL">卖出</option>
        </select>
      </label>
      <label className="form-field">
        <span>股数</span>
        <input name="shares" placeholder="输入股数" required step="0.01" type="number" />
      </label>
      <label className="form-field">
        <span>成交价</span>
        <input name="price" placeholder="输入价格" required step="0.01" type="number" />
      </label>
      <label className="form-field span-2">
        <span>交易理由</span>
        <select name="reason_category" defaultValue={reasons[0]}>
          {reasons.map((reason) => (
            <option key={reason} value={reason}>
              {reason}
            </option>
          ))}
        </select>
      </label>
      <label className="form-field span-2">
        <span>备注</span>
        <input name="note" placeholder="可选，补充说明" />
      </label>
      <div className="trade-form-actions">
        <Button>保存交易</Button>
        <span>{status}</span>
      </div>
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
