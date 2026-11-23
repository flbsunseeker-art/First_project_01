"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

export function LoadError({ message }: { message: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <div className="load-error" role="status">
      <span>{message}</span>
      <button className="button button-ghost" type="button" disabled={pending}
        onClick={() => startTransition(() => router.refresh())}>
        {pending ? "重试中…" : "重试"}
      </button>
    </div>
  );
}
