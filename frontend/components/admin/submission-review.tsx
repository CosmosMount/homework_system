"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { AttachmentDownloadButton } from "@/components/announcements/announcement-actions";
import { SafeHtml } from "@/components/announcements/safe-html";
import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type {
  ExcellentSubmissionSummary,
  Feedback,
  Submission,
} from "@/lib/api/types";
import { formatDateTime, formatFileSize } from "@/lib/format";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function SubmissionReview({
  assignmentTitle,
  initialSubmission,
  initialExcellent,
}: Readonly<{
  assignmentTitle: string;
  initialSubmission: Submission;
  initialExcellent: ExcellentSubmissionSummary[];
}>) {
  const router = useRouter();
  const [submission, setSubmission] = useState(initialSubmission);
  const [selectedId, setSelectedId] = useState(
    initialSubmission.latest_version_id,
  );
  const [excellentIds, setExcellentIds] = useState(
    () => new Set(initialExcellent.map((item) => item.version_id)),
  );
  const [feedbackMarkdown, setFeedbackMarkdown] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = useMemo(
    () =>
      submission.versions.find((version) => version.id === selectedId) ??
      submission.versions[0],
    [selectedId, submission.versions],
  );

  if (selected === undefined) {
    return <FormMessage>提交聚合中没有正式版本。</FormMessage>;
  }

  async function saveFeedback() {
    if (!feedbackMarkdown.trim()) {
      setError("评语正文不能为空。");
      return;
    }
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const feedback = await csrfFetch<Feedback>(
        "/admin/submissions/" +
          submission.id +
          "/versions/" +
          selected.id +
          "/feedback",
        {
          method: "PUT",
          body: JSON.stringify({
            body_markdown: feedbackMarkdown.trim(),
            revision: selected.feedback?.revision ?? null,
          }),
        },
      );
      setSubmission((current) => ({
        ...current,
        versions: current.versions.map((version) =>
          version.id === selected.id ? { ...version, feedback } : version,
        ),
      }));
      setFeedbackMarkdown("");
      setMessage("私密评语已保存；站内提醒不包含正文。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function toggleExcellent() {
    if (submission.assignment_id === null) {
      setError("赛事团队版本不能标记为优秀作业。");
      return;
    }
    setPending(true);
    setMessage(null);
    setError(null);
    const marked = excellentIds.has(selected.id);
    try {
      await csrfFetch(
        "/admin/assignments/" + submission.assignment_id +
          "/excellent-submissions/" +
          selected.id,
        { method: marked ? "DELETE" : "POST" },
      );
      setExcellentIds((current) => {
        const next = new Set(current);
        if (marked) next.delete(selected.id);
        else next.add(selected.id);
        return next;
      });
      setMessage(marked ? "已取消优秀标记。" : "已标记为本作业优秀版本。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-8 grid gap-8 xl:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <h2 className="text-lg font-semibold">版本</h2>
        <div className="mt-4 space-y-2">
          {submission.versions.map((version) => (
            <button
              className={
                "w-full border px-3 py-3 text-left " +
                (version.id === selected.id
                  ? "border-[var(--color-accent)]"
                  : "border-[var(--color-border)]")
              }
              key={version.id}
              onClick={() => {
                setSelectedId(version.id);
                setFeedbackMarkdown("");
                setError(null);
                setMessage(null);
              }}
              type="button"
            >
              <span className="font-medium">v{version.version_number}</span>
              <span className="mt-1 block font-mono text-xs text-[var(--color-text-muted)]">
                {formatDateTime(version.submitted_at)}
              </span>
            </button>
          ))}
        </div>
      </aside>

      <div className="space-y-6">
        {message ? <FormMessage tone="success">{message}</FormMessage> : null}
        {error ? <FormMessage>{error}</FormMessage> : null}

        <article className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--color-border)] pb-4">
            <div>
              <p className="font-mono text-xs text-[var(--color-accent)]">
                {assignmentTitle}
              </p>
              <h2 className="mt-2 text-2xl font-semibold">
                正式版本 v{selected.version_number}
              </h2>
            </div>
            {submission.assignment_id !== null ? (
              <button
                className={
                  "min-h-11 border px-4 text-sm " +
                  (excellentIds.has(selected.id)
                    ? "border-[var(--color-danger)] text-[var(--color-danger)]"
                    : "border-[var(--color-info)] text-[var(--color-info)]")
                }
                disabled={pending}
                onClick={toggleExcellent}
                type="button"
              >
                {excellentIds.has(selected.id) ? "取消优秀标记" : "标记为优秀"}
              </button>
            ) : (
              <span className="font-mono text-xs text-[var(--color-text-muted)]">
                TEAM SUBMISSION · NO SHOWCASE
              </span>
            )}
          </div>

          {selected.text_html ? (
            <div className="mt-6">
              <SafeHtml sanitizedHtml={selected.text_html} />
            </div>
          ) : null}
          {selected.external_url ? (
            <p className="mt-6">
              <a
                className="text-[var(--color-info)] underline underline-offset-4"
                href={selected.external_url}
                rel="noopener noreferrer"
                target="_blank"
              >
                打开外部提交链接 ↗
              </a>
            </p>
          ) : null}
          {selected.attachments.length ? (
            <section className="mt-6">
              <h3 className="text-lg font-medium">附件</h3>
              <div className="mt-3 space-y-2">
                {selected.attachments.map((attachment) => (
                  <div
                    className="flex flex-wrap items-center justify-between gap-4 border border-[var(--color-border)] p-3"
                    key={attachment.id}
                  >
                    <div>
                      <p className="text-sm font-medium">{attachment.file_name}</p>
                      <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                        {formatFileSize(attachment.size_bytes)}
                      </p>
                    </div>
                    <AttachmentDownloadButton fileId={attachment.id} />
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </article>

        <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <h2 className="text-xl font-semibold">私密评语</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            创建或修订后只通知个人提交者或当前团队成员“有新评语”，提醒和邮件不包含正文。
          </p>
          {selected.feedback ? (
            <div className="mt-5 border-l-2 border-[var(--color-info)] bg-[var(--color-bg)] p-4">
              <SafeHtml sanitizedHtml={selected.feedback.body_html} />
              <p className="mt-3 font-mono text-xs text-[var(--color-text-muted)]">
                revision {selected.feedback.revision} ·{" "}
                {formatDateTime(selected.feedback.updated_at)}
              </p>
            </div>
          ) : null}
          <label className="mt-5 block text-sm font-medium">
            {selected.feedback ? "替换评语 Markdown" : "评语 Markdown"}
            <textarea
              className={inputClassName + " min-h-48 py-3 font-mono text-sm"}
              disabled={pending}
              maxLength={200000}
              onChange={(event) => setFeedbackMarkdown(event.target.value)}
              value={feedbackMarkdown}
            />
          </label>
          <button
            className={buttonClassName + " mt-4"}
            disabled={pending}
            onClick={saveFeedback}
            type="button"
          >
            {pending ? "处理中…" : selected.feedback ? "修订评语" : "创建评语"}
          </button>
        </section>
      </div>
    </div>
  );
}
