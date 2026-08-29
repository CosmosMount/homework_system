"use client";

import { useState } from "react";

import { ApiError, csrfFetch } from "@/lib/api/client";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export { MarkNotificationsRead as MarkAnnouncementRead } from "@/components/notifications/mark-notifications-read";

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
