"use client";

import { usePathname } from "next/navigation";
import { PageLoading } from "../components/app-shell";

export default function Loading() {
  const pathname = usePathname();
  return <PageLoading pathname={pathname} />;
}
