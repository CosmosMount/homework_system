"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { AnnouncementUploader } from "@/components/announcements/announcement-uploader";
import { RenderedMarkdown } from "@/components/announcements/safe-html";
import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type {
  AnnouncementAdmin,
  CompletedFile,
  Direction,
} from "@/lib/api/types";
import { createIdempotencyKey } from "@/lib/idempotency";

function localDateTime(value: string | null): string {
  if (value === null) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function apiDateTime(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

function toggle(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function AnnouncementEditor({
  initialAnnouncement,
  directions,
}: Readonly<{
  initialAnnouncement: AnnouncementAdmin | null;
  directions: Direction[];
}>) {
  const router = useRouter();
  const [announcement, setAnnouncement] = useState(initialAnnouncement);
  const [title, setTitle] = useState(initialAnnouncement?.title ?? "");
  const [summary, setSummary] = useState(initialAnnouncement?.summary ?? "");
  const [bodyMarkdown, setBodyMarkdown] = useState(
    initialAnnouncement?.body_markdown ?? "",
  );
  const [allStudents, setAllStudents] = useState(
    initialAnnouncement?.audience.all_students ?? true,
  );
  // 历史通知可能仍带有届次受众；编辑时原样保留，避免覆盖历史受众。
  const legacyCohortIds = initialAnnouncement?.audience.cohort_ids ?? [];
  const [directionIds, setDirectionIds] = useState(
    initialAnnouncement?.audience.direction_ids ?? [],
  );
  const legacyAudienceMatch = initialAnnouncement?.audience.match ?? "intersection";
  const [publishAt, setPublishAt] = useState(
    localDateTime(initialAnnouncement?.publish_at ?? null),
  );
  const [pinnedUntil, setPinnedUntil] = useState(
    localDateTime(initialAnnouncement?.pinned_until ?? null),
  );
  const [sendEmail, setSendEmail] = useState(
    initialAnnouncement?.send_email ?? false,
  );
  const [attachmentIds, setAttachmentIds] = useState(
    initialAnnouncement?.attachment_file_ids ?? [],
  );
  const [uploadedNames, setUploadedNames] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function payload(revision?: number): Record<string, unknown> {
    return {
      ...(revision === undefined ? {} : { revision }),
      title: title.trim(),
      summary: summary.trim(),
      body_markdown: bodyMarkdown.trim(),
      audience: {
        all_students: allStudents,
        cohort_ids: allStudents ? [] : legacyCohortIds,
        direction_ids: allStudents ? [] : directionIds,
        match: legacyAudienceMatch,
      },
      attachment_file_ids: attachmentIds,
      publish_at: apiDateTime(publishAt),
      pinned_until: apiDateTime(pinnedUntil),
      send_email: sendEmail,
    };
  }

  function validate(): boolean {
    if (!title.trim() || !summary.trim() || !bodyMarkdown.trim()) {
      setError("标题、摘要和正文不能为空。");
      return false;
    }
    if (!allStudents && legacyCohortIds.length === 0 && directionIds.length === 0) {
      setError("定向通知至少需要选择一个技术方向。");
      return false;
    }
    return true;
  }

  async function persist(): Promise<AnnouncementAdmin> {
    if (!validate()) {
      throw new Error("FORM_INVALID");
    }
    const current = announcement;
    const saved = await csrfFetch<AnnouncementAdmin>(
      current === null
        ? "/admin/announcements"
        : "/admin/announcements/" + current.id,
      {
        method: current === null ? "POST" : "PATCH",
        body: JSON.stringify(payload(current?.revision)),
      },
    );
    setAnnouncement(saved);
    setAttachmentIds(saved.attachment_file_ids);
    if (current === null) {
      router.replace("/admin/announcements/" + saved.id + "/edit");
    }
    return saved;
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      await persist();
      setMessage("通知草稿已保存。");
      router.refresh();
    } catch (nextError) {
      if (!(nextError instanceof Error) || nextError.message !== "FORM_INVALID") {
        setError(errorMessage(nextError));
      }
    } finally {
      setPending(false);
    }
  }

  async function publish() {
    if (!window.confirm("确认发布？发布会为实际受众生成站内提醒，邮件会进入可靠队列。")) {
      return;
    }
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const saved = await persist();
      const published = await csrfFetch<AnnouncementAdmin>(
        "/admin/announcements/" + saved.id + "/publish",
        {
          method: "POST",
          headers: { "Idempotency-Key": createIdempotencyKey() },
        },
      );
      setAnnouncement(published);
      setMessage(
        published.status === "scheduled"
          ? "通知已安排定时发布。"
          : "通知已经发布。",
      );
      router.refresh();
    } catch (nextError) {
      if (!(nextError instanceof Error) || nextError.message !== "FORM_INVALID") {
        setError(errorMessage(nextError));
      }
    } finally {
      setPending(false);
    }
  }

  async function remove() {
    if (announcement === null) {
      return;
    }
    const prompt =
      announcement.status === "published"
        ? "确认删除通知？通知会立即从学生列表和详情隐藏，历史提醒与审计记录继续保留。"
        : "确认永久删除这条未发布通知？定时发布会取消，已绑定附件将进入孤立文件清理流程。";
    if (!window.confirm(prompt)) return;
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      await csrfFetch(
        "/admin/announcements/" + announcement.id,
        { method: "DELETE" },
      );
      router.replace("/admin/announcements");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function sendUpdate() {
    if (
      announcement === null ||
      !window.confirm("确认向当前受众发送这一 revision 的更新提醒？")
    ) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      const saved = await persist();
      const updated = await csrfFetch<AnnouncementAdmin>(
        "/admin/announcements/" + saved.id + "/send-update",
        {
          method: "POST",
          headers: { "Idempotency-Key": createIdempotencyKey() },
        },
      );
      setAnnouncement(updated);
      setMessage("更新提醒已写入站内提醒与邮件队列。");
      router.refresh();
    } catch (nextError) {
      if (!(nextError instanceof Error) || nextError.message !== "FORM_INVALID") {
        setError(errorMessage(nextError));
      }
    } finally {
      setPending(false);
    }
  }

  function addCompletedFile(file: CompletedFile) {
    setAttachmentIds((current) =>
      current.includes(file.file_id) ? current : [...current, file.file_id],
    );
    setUploadedNames((current) => ({
      ...current,
      [file.file_id]: file.file_name,
    }));
    setMessage("附件已完成校验；请保存通知以正式绑定。");
  }

  const editable = announcement?.status !== "archived";
  return (
    <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <form className="space-y-6" onSubmit={save}>
        {message ? <FormMessage tone="success">{message}</FormMessage> : null}
        {error ? <FormMessage>{error}</FormMessage> : null}

        <section className="space-y-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">内容</h2>
            <span className="font-mono text-xs text-[var(--color-text-muted)]">
              {announcement?.status ?? "new"} · revision {announcement?.revision ?? 0}
            </span>
          </div>
          <label className="block text-sm font-medium">
            标题
            <input
              className={inputClassName}
              disabled={!editable}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
              required
              value={title}
            />
          </label>
          <label className="block text-sm font-medium">
            摘要
            <textarea
              className={inputClassName + " min-h-24 py-3"}
              disabled={!editable}
              maxLength={500}
              onChange={(event) => setSummary(event.target.value)}
              required
              value={summary}
            />
          </label>
          <label className="block text-sm font-medium">
            Markdown 正文
            <textarea
              className={inputClassName + " min-h-80 py-3 font-mono text-sm"}
              disabled={!editable}
              maxLength={200000}
              onChange={(event) => setBodyMarkdown(event.target.value)}
              required
              value={bodyMarkdown}
            />
            <span className="mt-2 block text-xs text-[var(--color-text-muted)]">
              原始 HTML、远程图片和危险协议会被后端禁用或清洗。
            </span>
          </label>
        </section>

        <section className="space-y-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <h2 className="text-xl font-semibold">受众</h2>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                checked={allStudents}
                disabled={!editable}
                name="audience-mode"
                onChange={() => setAllStudents(true)}
                type="radio"
              />
              全部激活学生
            </label>
            <label className="flex items-center gap-2">
              <input
                checked={!allStudents}
                disabled={!editable}
                name="audience-mode"
                onChange={() => setAllStudents(false)}
                type="radio"
              />
              按技术方向
            </label>
          </div>
          {!allStudents ? (
            <div className="grid gap-6">
              <fieldset>
                <legend className="text-sm font-medium">方向</legend>
                <div className="mt-3 space-y-2">
                  {directions.map((direction) => (
                    <label className="flex items-center gap-2 text-sm" key={direction.id}>
                      <input
                        checked={directionIds.includes(direction.id)}
                        disabled={!editable || !direction.is_active}
                        onChange={() =>
                          setDirectionIds(toggle(directionIds, direction.id))
                        }
                        type="checkbox"
                      />
                      {direction.name}{direction.is_active ? "" : "（停用）"}
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>
          ) : null}
        </section>

        <section className="grid gap-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:grid-cols-2 sm:p-6">
          <h2 className="text-xl font-semibold sm:col-span-2">发布设置</h2>
          <label className="text-sm font-medium">
            定时发布时间
            <input
              className={inputClassName}
              disabled={!editable}
              onChange={(event) => setPublishAt(event.target.value)}
              type="datetime-local"
              value={publishAt}
            />
          </label>
          <label className="text-sm font-medium">
            置顶截止时间
            <input
              className={inputClassName}
              disabled={!editable}
              onChange={(event) => setPinnedUntil(event.target.value)}
              type="datetime-local"
              value={pinnedUntil}
            />
          </label>
          <label className="flex min-h-11 items-center gap-2 border border-[var(--color-border-strong)] px-4 text-sm sm:col-span-2">
            <input
              checked={sendEmail}
              disabled={!editable}
              onChange={(event) => setSendEmail(event.target.checked)}
              type="checkbox"
            />
            首次发布时同时写入逐学生邮件任务
          </label>
        </section>

        {announcement !== null && editable ? (
          <AnnouncementUploader
            announcementId={announcement.id}
            onCompleted={addCompletedFile}
          />
        ) : null}

        {attachmentIds.length ? (
          <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <h2 className="text-lg font-medium">待绑定附件</h2>
            <div className="mt-3 space-y-2">
              {attachmentIds.map((fileId) => (
                <div
                  className="flex flex-wrap items-center justify-between gap-3 border border-[var(--color-border)] p-3"
                  key={fileId}
                >
                  <span className="text-sm">
                    {uploadedNames[fileId] ?? fileId}
                  </span>
                  {editable ? (
                    <button
                      className="text-sm text-[var(--color-danger)]"
                      onClick={() =>
                        setAttachmentIds((current) =>
                          current.filter((item) => item !== fileId),
                        )
                      }
                      type="button"
                    >
                      移除
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {editable ? (
          <div className="flex flex-wrap gap-3">
            <button className={buttonClassName} disabled={pending} type="submit">
              {pending ? "处理中…" : "保存草稿"}
            </button>
            <button
              className="min-h-11 border border-[var(--color-accent)] px-5 font-medium text-[var(--color-accent-hover)] disabled:opacity-55"
              disabled={pending}
              onClick={publish}
              type="button"
            >
              {publishAt ? "保存并安排发布" : "保存并立即发布"}
            </button>
            {announcement?.status === "published" ? (
              <button
                className="min-h-11 border border-[var(--color-border-strong)] px-5 disabled:opacity-55"
                disabled={pending}
                onClick={sendUpdate}
                type="button"
              >
                保存并发送更新提醒
              </button>
            ) : null}
            {announcement ? (
              <button
                className="min-h-11 border border-[var(--color-danger)] px-5 text-[var(--color-danger)] disabled:opacity-55"
                disabled={pending}
                onClick={remove}
                type="button"
              >
                删除通知
              </button>
            ) : null}
          </div>
        ) : null}
      </form>

      <aside className="space-y-5">
        <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 xl:sticky xl:top-5">
          <p className="font-mono text-xs text-[var(--color-text-muted)]">
            DELIVERY SNAPSHOT
          </p>
          <dl className="mt-4 space-y-4 text-sm">
            <div>
              <dt className="text-[var(--color-text-muted)]">预计接收</dt>
              <dd className="mt-1 text-2xl font-semibold">
                {announcement?.estimated_recipient_count ?? "保存后计算"}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--color-text-muted)]">实际发布快照</dt>
              <dd className="mt-1">
                {announcement?.actual_recipient_count ?? 0} 人
              </dd>
            </div>
          </dl>
          {announcement?.body_html ? (
            <div className="mt-6 border-t border-[var(--color-border)] pt-5">
              <RenderedMarkdown sanitizedHtml={announcement.body_html} />
            </div>
          ) : (
            <p className="mt-6 text-xs text-[var(--color-text-muted)]">
              保存后会生成与学生详情一致的内容。
            </p>
          )}
        </section>
      </aside>
    </div>
  );
}
