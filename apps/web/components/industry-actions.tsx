"use client";

import { useState } from "react";

import { apiSend } from "../lib/api";

export function IndustryEditor({
  securityId,
  defaultIndustry,
}: Readonly<{ securityId: number; defaultIndustry: string }>) {
  const [status, setStatus] = useState("");

  async function submit(formData: FormData) {
    setStatus("保存中...");
    try {
      await apiSend("PATCH", `/api/v1/securities/${securityId}/industry`, {
        industry: formData.get("industry"),
      });
      setStatus("已保存，刷新后生效");
    } catch {
      setStatus("保存失败");
    }
  }

  return (
    <form action={submit} className="inline-form">
      <input defaultValue={defaultIndustry} name="industry" />
      <button className="inline-action" type="submit">
        保存
      </button>
      <span>{status}</span>
    </form>
  );
}
