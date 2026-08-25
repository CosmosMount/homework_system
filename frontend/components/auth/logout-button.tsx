"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { clearCsrfToken, csrfFetch } from "@/lib/api/client";

export function LogoutButton() {
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
      className="text-left hover:text-[var(--color-text-primary)] disabled:opacity-50"
      disabled={pending}
      onClick={logout}
      type="button"
    >
      {pending ? "退出中…" : "退出登录"}
    </button>
  );
}
