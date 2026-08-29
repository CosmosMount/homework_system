"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError, csrfFetch } from "@/lib/api/client";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "标记已读失败，请稍后重试。";
}

export function MarkNotificationsRead({
  notificationIds,
}: Readonly<{ notificationIds: string[] }>) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const notificationKey = notificationIds.join(",");

  useEffect(() => {
    if (!notificationKey) return;
    let cancelled = false;

    async function markRead() {
      try {
        await Promise.all(
          notificationKey.split(",").map((notificationId) =>
            csrfFetch("/notifications/" + notificationId + "/read", {
              method: "POST",
            }),
          ),
        );
        if (!cancelled) router.refresh();
      } catch (nextError) {
        if (!cancelled) setError(errorMessage(nextError));
      }
    }

    void markRead();
    return () => {
      cancelled = true;
    };
  }, [notificationKey, router]);

  if (!notificationKey) return null;

  return error ? (
    <p aria-live="polite" className="text-sm text-[var(--color-danger)]">
      {error}
    </p>
  ) : (
    <p aria-live="polite" className="text-sm text-[var(--color-text-muted)]">
      正在同步已读状态…
    </p>
  );
}
