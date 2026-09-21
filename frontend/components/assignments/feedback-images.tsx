"use client";

/* eslint-disable @next/next/no-img-element -- 登录态内容入口会跳转到短时签名地址，不适合 Next 图片优化。 */

import { useState } from "react";

import { AttachmentDownloadButton } from "@/components/announcements/announcement-actions";
import type { SubmissionAttachment } from "@/lib/api/types";
import { formatFileSize } from "@/lib/format";

export function FeedbackImages({
  images,
}: Readonly<{ images: SubmissionAttachment[] }>) {
  const [attempts, setAttempts] = useState<Record<string, number>>({});
  const [failedIds, setFailedIds] = useState<Set<string>>(() => new Set());

  if (images.length === 0) return null;

  function retry(fileId: string) {
    setFailedIds((current) => {
      const next = new Set(current);
      next.delete(fileId);
      return next;
    });
    setAttempts((current) => ({
      ...current,
      [fileId]: (current[fileId] ?? 0) + 1,
    }));
  }

  function markFailed(fileId: string) {
    setFailedIds((current) => new Set(current).add(fileId));
  }

  return (
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      {images.map((image) => {
        const failed = failedIds.has(image.id);
        const attempt = attempts[image.id] ?? 0;
        return (
          <figure
            className="min-w-0 overflow-hidden border border-[var(--color-border)] bg-[var(--color-surface)]"
            key={image.id}
          >
            <div className="flex min-h-48 items-center justify-center bg-[var(--color-bg)] p-2">
              {failed ? (
                <div className="px-4 py-8 text-center">
                  <p className="text-sm text-[var(--color-danger)]">
                    图片加载失败，可以重试或下载查看。
                  </p>
                  <button
                    className="mt-3 min-h-10 border border-[var(--color-border-strong)] px-4 text-sm"
                    onClick={() => retry(image.id)}
                    type="button"
                  >
                    重新加载
                  </button>
                </div>
              ) : (
                <img
                  alt={image.file_name}
                  className="max-h-[32rem] w-full object-contain"
                  loading="lazy"
                  onError={() => markFailed(image.id)}
                  src={
                    "/api/v1/files/" +
                    encodeURIComponent(image.id) +
                    "/content?attempt=" +
                    attempt
                  }
                />
              )}
            </div>
            <figcaption className="border-t border-[var(--color-border)] p-3">
              <p className="break-words text-sm font-medium">
                {image.file_name}
              </p>
              <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                {formatFileSize(image.size_bytes)}
              </p>
              <div className="mt-3">
                <AttachmentDownloadButton
                  fileId={image.id}
                  fileName={image.file_name}
                  mediaType={image.media_type}
                />
              </div>
            </figcaption>
          </figure>
        );
      })}
    </div>
  );
}
