"use client";

/* eslint-disable @next/next/no-img-element -- 预签名附件尺寸未知且短时 URL 不适合 Next 图片优化。 */

import { useEffect, useRef, useState } from "react";

import { ApiError, csrfFetch } from "@/lib/api/client";

type PreviewKind = "image" | "pdf" | "text" | "video";

const TEXT_EXTENSIONS = new Set([
  "c",
  "cpp",
  "csv",
  "go",
  "h",
  "hpp",
  "java",
  "json",
  "kt",
  "md",
  "py",
  "rs",
  "txt",
]);

const PREVIEW_MEDIA_TYPES_BY_EXTENSION: Record<string, string> = {
  gif: "image/gif",
  jpeg: "image/jpeg",
  jpg: "image/jpeg",
  mp4: "video/mp4",
  pdf: "application/pdf",
  png: "image/png",
  webm: "video/webm",
  webp: "image/webp",
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

function previewKind(fileName: string, mediaType: string): PreviewKind | null {
  const extension = fileName.toLowerCase().split(".").pop() ?? "";
  if (mediaType === "text/plain" && TEXT_EXTENSIONS.has(extension)) {
    return "text";
  }
  if (PREVIEW_MEDIA_TYPES_BY_EXTENSION[extension] !== mediaType) {
    return null;
  }
  if (mediaType === "application/pdf") return "pdf";
  if (mediaType.startsWith("image/")) return "image";
  if (mediaType.startsWith("video/")) return "video";
  return null;
}

export { MarkNotificationsRead as MarkAnnouncementRead } from "@/components/notifications/mark-notifications-read";

export function AttachmentDownloadButton({
  fileId,
  fileName,
  mediaType,
}: Readonly<{
  fileId: string;
  fileName: string;
  mediaType: string;
}>) {
  const kind = previewKind(fileName, mediaType);
  const previewTriggerRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [downloadPending, setDownloadPending] = useState(false);
  const [downloadMessage, setDownloadMessage] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewPending, setPreviewPending] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  function closePreview() {
    setPreviewOpen(false);
    setPreviewPending(false);
    setPreviewUrl(null);
    setPreviewError(null);
    previewTriggerRef.current?.focus();
  }

  useEffect(() => {
    if (!previewOpen) return;
    closeButtonRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closePreview();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [previewOpen]);

  async function download() {
    setDownloadPending(true);
    setDownloadMessage(null);
    try {
      const result = await csrfFetch<{ url: string }>(
        "/files/" + fileId + "/download-url",
        { method: "POST" },
      );
      window.location.assign(result.url);
      setDownloadPending(false);
    } catch (error) {
      setDownloadMessage(errorMessage(error));
      setDownloadPending(false);
    }
  }

  async function loadPreview() {
    if (kind === null) return;
    setPreviewOpen(true);
    setPreviewPending(true);
    setPreviewUrl(null);
    setPreviewError(null);
    try {
      const result = await csrfFetch<{ url: string }>(
        "/files/" + fileId + "/preview-url",
        { method: "POST" },
      );
      setPreviewUrl(result.url);
    } catch (error) {
      setPreviewError(errorMessage(error));
    } finally {
      setPreviewPending(false);
    }
  }

  function markPreviewLoadFailed() {
    setPreviewUrl(null);
    setPreviewError("附件预览加载失败，请重试或下载后查看。");
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {kind ? (
          <button
            className="min-h-10 border border-[var(--color-accent)] px-4 text-sm text-[var(--color-accent)] disabled:opacity-55"
            disabled={previewPending}
            onClick={() => void loadPreview()}
            ref={previewTriggerRef}
            type="button"
          >
            {previewPending ? "准备预览…" : "预览附件"}
          </button>
        ) : null}
        <button
          className="min-h-10 border border-[var(--color-border-strong)] px-4 text-sm disabled:opacity-55"
          disabled={downloadPending}
          onClick={() => void download()}
          type="button"
        >
          {downloadPending ? "准备下载…" : "下载附件"}
        </button>
      </div>
      {downloadMessage ? (
        <p aria-live="polite" className="mt-2 text-xs text-[var(--color-danger)]">
          {downloadMessage}
        </p>
      ) : null}

      {previewOpen && kind ? (
        <div
          aria-label={fileName + " 预览"}
          aria-modal="true"
          className="fixed inset-0 z-[70] flex items-center justify-center p-4 sm:p-8"
          role="dialog"
        >
          <button
            aria-label="关闭附件预览"
            className="absolute inset-0 bg-slate-950/60"
            onClick={closePreview}
            type="button"
          />
          <div className="relative flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-soft)]">
            <header className="flex shrink-0 items-center justify-between gap-4 border-b border-[var(--color-border)] px-4 py-3 sm:px-5">
              <div className="min-w-0">
                <h2 className="truncate font-semibold">{fileName}</h2>
                <p className="mt-0.5 font-mono text-xs text-[var(--color-text-muted)]">
                  {mediaType}
                </p>
              </div>
              <button
                className="min-h-10 shrink-0 border border-[var(--color-border-strong)] px-4 text-sm"
                onClick={closePreview}
                ref={closeButtonRef}
                type="button"
              >
                关闭
              </button>
            </header>
            <div className="flex min-h-[18rem] flex-1 items-center justify-center overflow-auto bg-[var(--color-bg)] p-3 sm:min-h-[32rem] sm:p-5">
              {previewPending ? (
                <p aria-live="polite" className="text-sm text-[var(--color-text-muted)]">
                  正在加载附件预览…
                </p>
              ) : null}
              {previewError ? (
                <div className="text-center">
                  <p aria-live="polite" className="text-sm text-[var(--color-danger)]">
                    {previewError}
                  </p>
                  <button
                    className="mt-4 min-h-10 border border-[var(--color-border-strong)] px-4 text-sm"
                    onClick={() => void loadPreview()}
                    type="button"
                  >
                    重新加载
                  </button>
                </div>
              ) : null}
              {previewUrl && kind === "image" ? (
                <img
                  alt={fileName}
                  className="max-h-[75vh] max-w-full object-contain"
                  onError={markPreviewLoadFailed}
                  src={previewUrl}
                />
              ) : null}
              {previewUrl && kind === "video" ? (
                <video
                  aria-label={fileName}
                  className="max-h-[75vh] max-w-full"
                  controls
                  onError={markPreviewLoadFailed}
                  src={previewUrl}
                />
              ) : null}
              {previewUrl && (kind === "pdf" || kind === "text") ? (
                <iframe
                  className="h-[70vh] min-h-[28rem] w-full border-0 bg-white"
                  onError={markPreviewLoadFailed}
                  referrerPolicy="no-referrer"
                  src={previewUrl}
                  title={fileName + " 预览内容"}
                />
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
