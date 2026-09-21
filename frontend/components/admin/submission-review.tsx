"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { AttachmentDownloadButton } from "@/components/announcements/announcement-actions";
import { SafeHtml } from "@/components/announcements/safe-html";
import { FeedbackImages } from "@/components/assignments/feedback-images";
import { MultipartUploader } from "@/components/uploads/multipart-uploader";
import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type {
  ExcellentSubmissionSummary,
  Feedback,
  CompletedFile,
  Submission,
  SubmissionAttachment,
  SubmissionCompletion,
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
  const [feedbackImageDrafts, setFeedbackImageDrafts] = useState<
    Record<string, SubmissionAttachment[]>
  >(() =>
    Object.fromEntries(
      initialSubmission.versions.map((version) => [
        version.id,
        version.feedback?.images ?? [],
      ]),
    ),
  );
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = useMemo(
    () =>
      submission.versions.find((version) => version.id === selectedId) ??
      submission.versions[0],
    [selectedId, submission.versions],
  );
  const completedVersion = submission.completed_version_id
    ? submission.versions.find(
        (version) => version.id === submission.completed_version_id,
      )
    : undefined;
  const feedbackImages = selected ? (feedbackImageDrafts[selected.id] ?? []) : [];
  const feedbackImageBytes = feedbackImages.reduce(
    (total, image) => total + image.size_bytes,
    0,
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
            file_ids: feedbackImages.map((image) => image.id),
          }),
        },
      );
      setSubmission((current) => ({
        ...current,
        versions: current.versions.map((version) =>
          version.id === selected.id ? { ...version, feedback } : version,
        ),
      }));
      setFeedbackImageDrafts((current) => ({
        ...current,
        [selected.id]: feedback.images,
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

  function addFeedbackImage(file: CompletedFile) {
    setFeedbackImageDrafts((current) => {
      const existing = current[selected.id] ?? [];
      if (existing.some((image) => image.id === file.file_id)) return current;
      return {
        ...current,
        [selected.id]: [
          ...existing,
          {
            id: file.file_id,
            file_name: file.file_name,
            size_bytes: file.size_bytes,
            media_type: file.media_type,
            sha256: file.sha256,
          },
        ],
      };
    });
  }

  function removeFeedbackImage(fileId: string) {
    setFeedbackImageDrafts((current) => ({
      ...current,
      [selected.id]: (current[selected.id] ?? []).filter(
        (image) => image.id !== fileId,
      ),
    }));
  }

  async function toggleExcellent() {
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
  async function toggleCompletion() {
    const revoking = submission.is_completed;
    const latestVersion = submission.versions.find(
      (version) => version.id === submission.latest_version_id,
    );
    const prompt = revoking
      ? "确认撤销当前最新版本的完成确认？"
      : `确认已审阅并完成 v${latestVersion?.version_number ?? "最新"}？学生提交新版本后需要重新确认。`;
    if (!window.confirm(prompt)) return;

    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const completion = await csrfFetch<SubmissionCompletion>(
        "/admin/submissions/" + submission.id + "/completion",
        { method: revoking ? "DELETE" : "POST" },
      );
      setSubmission((current) => ({
        ...current,
        completed_version_id: completion.completed_version_id,
        completed_at: completion.completed_at,
        is_completed: completion.is_completed,
      }));
      setMessage(revoking ? "已撤销完成确认。" : "已确认当前最新版本完成。");
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
              <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                {submission.is_completed
                  ? `最新 v${completedVersion?.version_number ?? "—"} 已由管理员确认完成 · ${submission.completed_at ? formatDateTime(submission.completed_at) : "时间未知"}`
                  : completedVersion
                    ? `v${completedVersion.version_number} 曾确认完成；最新版本已更新，需重新确认。`
                    : "当前最新版本尚未确认完成。"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className={
                  "min-h-11 border px-4 text-sm " +
                  (submission.is_completed
                    ? "border-[var(--color-danger)] text-[var(--color-danger)]"
                    : "border-[var(--color-accent)] bg-[var(--color-accent)] text-white")
                }
                disabled={pending}
                onClick={toggleCompletion}
                type="button"
              >
                {submission.is_completed ? "撤销完成确认" : "确认最新版本完成"}
              </button>
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
            </div>
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
                    <AttachmentDownloadButton
                      fileId={attachment.id}
                      fileName={attachment.file_name}
                      mediaType={attachment.media_type}
                    />
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </article>

        <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <h2 className="text-xl font-semibold">私密评语</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            创建或修订后只通知个人提交者“有新评语”，提醒和邮件不包含正文。
          </p>
          {selected.feedback ? (
            <div className="mt-5 border-l-2 border-[var(--color-info)] bg-[var(--color-bg)] p-4">
              <SafeHtml sanitizedHtml={selected.feedback.body_html} />
              <FeedbackImages images={selected.feedback.images} />
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
          <div className="mt-5">
            <MultipartUploader
              accept=".png,.jpg,.jpeg,.gif,.webp"
              contextId={selected.id}
              description="仅支持 PNG、JPEG、GIF、WebP；单张不超过 10 MiB，最多 10 张、合计不超过 50 MiB。上传完成后仍需保存评语。"
              heading="上传评语图片"
              key={selected.id}
              maxBytes={10 * 1024 * 1024}
              maxSelectedBytes={Math.max(
                50 * 1024 * 1024 - feedbackImageBytes,
                0,
              )}
              maxSelectedFiles={Math.max(10 - feedbackImages.length, 0)}
              multiple
              onCompleted={addFeedbackImage}
              purpose="submission_feedback"
            />
          </div>
          {feedbackImages.length ? (
            <section className="mt-4 border border-[var(--color-border)] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-medium">随本次评语保存的图片</h3>
                <span className="font-mono text-xs text-[var(--color-text-muted)]">
                  {feedbackImages.length} / 10 · {formatFileSize(feedbackImageBytes)} / 50 MiB
                </span>
              </div>
              <div className="mt-3 space-y-2">
                {feedbackImages.map((image) => (
                  <div
                    className="flex flex-wrap items-center justify-between gap-3 border border-[var(--color-border)] p-3"
                    key={image.id}
                  >
                    <span className="break-all text-sm">
                      {image.file_name} · {formatFileSize(image.size_bytes)}
                    </span>
                    <button
                      className="min-h-10 text-sm text-[var(--color-danger)]"
                      disabled={pending}
                      onClick={() => removeFeedbackImage(image.id)}
                      type="button"
                    >
                      移除
                    </button>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
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
