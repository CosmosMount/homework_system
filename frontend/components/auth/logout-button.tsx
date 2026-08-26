"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { clearCsrfToken, csrfFetch } from "@/lib/api/client";

export function LogoutButton({ collapsed = false }: Readonly<{ collapsed?: boolean }>) {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function logout() {
    setPending(true);
    try {
      await csrfFetch<void>("/auth/logout", { method: "POST" });
    } finally {
      clearCsrfToken();
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <button
      className={"flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] disabled:cursor-not-allowed disabled:opacity-50 " + (collapsed ? "justify-center px-0" : "")}
      disabled={pending}
      onClick={logout}
      type="button"
    >
      <span aria-hidden="true" className="w-7 shrink-0 text-center text-sm">↪</span>
      <span className={collapsed ? "sr-only" : ""}>{pending ? "退出中…" : "退出登录"}</span>
    </button>
  );
}
