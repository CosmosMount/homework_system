"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, csrfFetch } from "@/lib/api/client";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function MarkAnnouncementRead({
  notificationIds,
}: Readonly<{ notificationIds: string[] }>) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function markRead() {
    setPending(true);
    setMessage(null);
    try {
      await Promise.all(
        notificationIds.map((notificationId) =>
          csrfFetch("/notifications/" + notificationId + "/read", {
            method: "POST",
          }),
        ),
      );
      setMessage("相关提醒已标记为已读。");
      router.refresh();
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setPending(false);
    }
  }

  if (notificationIds.length === 0) {
    return null;
  }

  return (
    <div>
      <button
        className="min-h-11 border border-[var(--color-border-strong)] px-4 text-sm disabled:opacity-55"
        disabled={pending}
        onClick={markRead}
        type="button"
      >
        {pending ? "正在更新…" : "将相关提醒标为已读"}
      </button>
      {message ? (
        <p aria-live="polite" className="mt-2 text-xs text-[var(--color-text-muted)]">
          {message}
        </p>
      ) : null}
    </div>
  );
}

export function AttachmentDownloadButton({
  fileId,
}: Readonly<{ fileId: string }>) {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function download() {
    setPending(true);
    setMessage(null);
    try {
      const result = await csrfFetch<{ url: string }>(
        "/files/" + fileId + "/download-url",
        { method: "POST" },
      );
      window.location.assign(result.url);
    } catch (error) {
      setMessage(errorMessage(error));
      setPending(false);
    }
  }

  return (
    <div>
      <button
        className="min-h-10 border border-[var(--color-border-strong)] px-4 text-sm disabled:opacity-55"
        disabled={pending}
        onClick={download}
        type="button"
      >
        {pending ? "准备下载…" : "下载附件"}
      </button>
      {message ? (
        <p aria-live="polite" className="mt-2 text-xs text-[var(--color-danger)]">
          {message}
        </p>
      ) : null}
    </div>
  );
}
