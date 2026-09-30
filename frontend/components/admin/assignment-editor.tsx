"use client";

import Link from "next/link";
import { type FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { RenderedMarkdown } from "@/components/announcements/safe-html";
import { KnowledgeReferencePicker } from "@/components/knowledge/knowledge-reference-picker";
import { AppIcon, type AppIconName } from "@/components/ui/app-icon";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type {
  AssignmentAdmin,
  AssignmentSubmissionAdminItem,
  Direction,
} from "@/lib/api/types";
import { formatDateTime, formatFileSize } from "@/lib/format";
import { createIdempotencyKey } from "@/lib/idempotency";
import { insertMarkdownAtSelection } from "@/lib/knowledge-references";

function localDateTime(value: string | null): string {
  if (value === null) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function apiDateTime(value: string): string {
  return new Date(value).toISOString();
}

function toggle(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

async function assignmentAdminFetch<T>(
  path: string,
  init: RequestInit,
): Promise<T> {
  try {
    return await csrfFetch<T>(path, init);
  } catch (error) {
    if (
      !(error instanceof ApiError) ||
      error.code !== "FORBIDDEN" ||
      (path !== "/admin/assignments" &&
        !path.startsWith("/admin/assignments/"))
    ) {
      throw error;
    }
    await csrfFetch("/auth/student-view", { method: "DELETE" });
    return csrfFetch<T>(path, init);
  }
}

function SubmissionStatusList({
  items,
}: Readonly<{
  items: AssignmentSubmissionAdminItem[];
}>) {
  return (
    <div className="mt-5 overflow-hidden border border-[var(--color-border)]">
      <div className="hidden grid-cols-[minmax(0,1fr)_9rem_8rem] gap-3 bg-[var(--color-surface-raised)] px-4 py-2 text-xs text-[var(--color-text-muted)] sm:grid"><span>学生</span><span>状态</span><span>提交</span></div>
      {items.length === 0 ? (
        <p className="p-4 text-sm text-[var(--color-text-muted)]">暂无目标学生。</p>
      ) : (
        <div className="divide-y divide-[var(--color-border)]">
          {items.map((item) => (
            <article className="grid gap-3 bg-[var(--color-surface)] p-4 sm:grid-cols-[minmax(0,1fr)_9rem_8rem] sm:items-center" key={item.user_id}>
                <div>
                  <p className="font-medium">{item.full_name}</p>
                  <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                    {item.student_number}
                  </p>
                </div>
                <StatusBadge item={item} />
                {item.submission_id ? (
                  <Link
                    className="text-sm text-[var(--color-info)] sm:text-right"
                    href={"/admin/submissions/" + item.submission_id}
                  >
                    查看 v{item.latest_version_number} →
                  </Link>
                ) : (
                  <span className="text-sm text-[var(--color-text-muted)]">
                    未提交
                  </span>
                )}
              {item.completed_at ? <p className="text-xs text-[var(--color-text-secondary)] sm:col-span-3">{item.is_completed ? "当前版本确认于 " : "历史版本确认于 "}{formatDateTime(item.completed_at)}</p> : null}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ item }: Readonly<{ item: AssignmentSubmissionAdminItem }>) {
  const status: { label: string; icon: AppIconName; className: string } = item.is_completed
    ? { label: "已完成", icon: "audit", className: "text-[var(--color-success)]" }
    : item.has_feedback
      ? { label: "待修改", icon: "mail", className: "text-[var(--color-warning)]" }
      : item.submission_id
        ? { label: "已提交", icon: "layers", className: "text-[var(--color-info)]" }
        : { label: "未提交", icon: "monitor", className: "text-[var(--color-text-muted)]" };
  return <span className={`inline-flex items-center gap-2 text-sm font-medium ${status.className}`}><AppIcon name={status.icon} size={16} aria-hidden="true" />{status.label}</span>;
}

type SubmissionFilter = "all" | "unsubmitted" | "submitted" | "feedback" | "completed";

function matchesFilter(item: AssignmentSubmissionAdminItem, filter: SubmissionFilter): boolean {
  if (filter === "all") return true;
  if (filter === "completed") return item.is_completed;
  if (filter === "feedback") return item.has_feedback && !item.is_completed;
  if (filter === "submitted") return Boolean(item.submission_id) && !item.has_feedback && !item.is_completed;
  return item.submission_id === null;
}

export function AssignmentEditor({
  initialAssignment,
  initialSubmissions,
  directions,
}: Readonly<{
  initialAssignment: AssignmentAdmin | null;
  initialSubmissions: AssignmentSubmissionAdminItem[];
  directions: Direction[];
}>) {
  const router = useRouter();
  const descriptionInputRef = useRef<HTMLTextAreaElement>(null);
  const [assignment, setAssignment] = useState(initialAssignment);
  const [submissionFilter, setSubmissionFilter] = useState<SubmissionFilter>("all");
  const [title, setTitle] = useState(initialAssignment?.title ?? "");
  const [descriptionMarkdown, setDescriptionMarkdown] = useState(
    initialAssignment?.description_markdown ?? "",
  );
  const [trainingUrl, setTrainingUrl] = useState(
    initialAssignment?.training_url ?? "",
  );
  const [instructions, setInstructions] = useState(
    initialAssignment?.submission_instructions ?? "",
  );
  const [allStudents, setAllStudents] = useState(
    initialAssignment?.audience.all_students ?? true,
  );
  // 历史作业可能仍带有届次受众；编辑时原样保留，避免覆盖历史受众。
  const legacyCohortIds = initialAssignment?.audience.cohort_ids ?? [];
  const [directionIds, setDirectionIds] = useState(
    initialAssignment?.audience.direction_ids ?? [],
  );
  const legacyAudienceMatch = initialAssignment?.audience.match ?? "intersection";
  const [allowedExtensions, setAllowedExtensions] = useState(
    initialAssignment?.allowed_extensions.join(", ") ?? "pdf, zip",
  );
  const [maxTotalBytes, setMaxTotalBytes] = useState(
    String(initialAssignment?.max_total_bytes ?? 2_147_483_648),
  );
  const [publishAt, setPublishAt] = useState(
    localDateTime(initialAssignment?.publish_at ?? new Date().toISOString()),
  );
  const [pending, setPending] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function extensionList(): string[] {
    return allowedExtensions
      .split(",")
      .map((extension) => extension.trim().toLowerCase().replace(/^\./, ""))
      .filter(Boolean);
  }

  function validate(): boolean {
    if (!title.trim() || !descriptionMarkdown.trim() || !instructions.trim()) {
      setError("标题、作业说明和提交说明不能为空。");
      return false;
    }
    if (!publishAt) {
      setError("发布时间不能为空。");
      return false;
    }
    if (!allStudents && legacyCohortIds.length === 0 && directionIds.length === 0) {
      setError("定向作业至少需要选择一个技术方向。");
      return false;
    }
    if (extensionList().length === 0) {
      setError("至少需要一个允许扩展名。");
      return false;
    }
    const byteLimit = Number(maxTotalBytes);
    if (
      !Number.isSafeInteger(byteLimit) ||
      byteLimit < 1 ||
      byteLimit > 2_147_483_648
    ) {
      setError("附件上限必须是 1 到 2147483648 之间的整数。");
      return false;
    }
    return true;
  }

  function payload(revision?: number): Record<string, unknown> {
    const lockedConfiguration =
      assignment !== null && assignment.status !== "draft";
    return {
      ...(revision === undefined ? {} : { revision }),
      title: title.trim(),
      description_markdown: descriptionMarkdown.trim(),
      training_url: trainingUrl.trim() || null,
      submission_instructions: instructions.trim(),
      audience: {
        all_students: allStudents,
        cohort_ids: allStudents ? [] : legacyCohortIds,
        direction_ids: allStudents ? [] : directionIds,
        match: legacyAudienceMatch,
      },
      allowed_extensions: lockedConfiguration
        ? assignment.allowed_extensions
        : extensionList(),
      max_total_bytes: lockedConfiguration
        ? assignment.max_total_bytes
        : Number(maxTotalBytes),
      publish_at: lockedConfiguration
        ? assignment.publish_at
        : apiDateTime(publishAt),
    };
  }

  async function persist(): Promise<AssignmentAdmin> {
    if (!validate()) throw new Error("FORM_INVALID");
    const current = assignment;
    const saved = await assignmentAdminFetch<AssignmentAdmin>(
      current === null
        ? "/admin/assignments"
        : "/admin/assignments/" + current.id,
      {
        method: current === null ? "POST" : "PATCH",
        body: JSON.stringify(payload(current?.revision)),
      },
    );
    setAssignment(saved);
    setDirty(false);
    if (current === null) {
      router.replace("/admin/assignments/" + saved.id + "/edit");
    }
    return saved;
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const savingDraft = assignment === null || assignment.status === "draft";
      await persist();
      setMessage(savingDraft ? "作业草稿已保存。" : "作业已更新。");
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
    if (!window.confirm("确认发布？发布会固化逐学生受众快照。")) return;
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const saved = await persist();
      const result = await assignmentAdminFetch<AssignmentAdmin>(
        "/admin/assignments/" + saved.id + "/publish",
        {
          method: "POST",
          headers: { "Idempotency-Key": createIdempotencyKey() },
        },
      );
      setAssignment(result);
      setMessage(
        result.status === "draft"
          ? "作业已安排定时发布。"
          : "作业已发布并固化受众快照。",
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

  async function close() {
    if (assignment === null) return;
    if (!window.confirm("确认提前关闭？关闭后目标学生将不能继续提交。")) return;
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const result = await assignmentAdminFetch<AssignmentAdmin>(
        "/admin/assignments/" + assignment.id + "/close",
        { method: "POST" },
      );
      setAssignment(result);
      setMessage("作业已关闭。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function reopen() {
    if (assignment === null) return;
    if (!window.confirm("确认重新打开？目标学生将可以继续提交作业。")) return;
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const result = await assignmentAdminFetch<AssignmentAdmin>(
        "/admin/assignments/" + assignment.id + "/reopen",
        { method: "POST" },
      );
      setAssignment(result);
      setMessage("作业已重新打开。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function sendEmailReminder() {
    if (
      assignment === null ||
      !window.confirm("确认向当前作业受众发送邮件提醒？同一版本重复点击不会重复发送。")
    ) {
      return;
    }
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const saved = dirty ? await persist() : assignment;
      if (saved === null) return;
      const reminded = await assignmentAdminFetch<AssignmentAdmin>(
        "/admin/assignments/" + saved.id + "/send-email",
        {
          method: "POST",
          headers: { "Idempotency-Key": createIdempotencyKey() },
        },
      );
      setAssignment(reminded);
      setMessage("邮件提醒已写入发送队列。相同版本重复操作不会重复发送。");
      router.refresh();
    } catch (nextError) {
      if (!(nextError instanceof Error) || nextError.message !== "FORM_INVALID") {
        setError(errorMessage(nextError));
      }
    } finally {
      setPending(false);
    }
  }

  function insertKnowledgeDocument(snippet: string) {
    const input = descriptionInputRef.current;
    const next = insertMarkdownAtSelection(
      descriptionMarkdown,
      snippet,
      input?.selectionStart ?? descriptionMarkdown.length,
      input?.selectionEnd ?? descriptionMarkdown.length,
    );
    setDescriptionMarkdown(next.value);
    setDirty(true);
    requestAnimationFrame(() => {
      input?.focus();
      input?.setSelectionRange(next.cursor, next.cursor);
    });
    setMessage("知识库文档引用已插入作业说明。");
  }

  async function remove() {
    if (assignment === null) return;
    const prompt =
      assignment.status === "draft"
        ? "确认永久删除这份未发布作业？定时发布会一并取消。"
        : "确认删除作业？作业会立即从学生列表、详情和优秀作业入口隐藏，正式提交与审计记录继续保留。";
    if (!window.confirm(prompt)) return;
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      await assignmentAdminFetch(
        "/admin/assignments/" + assignment.id,
        { method: "DELETE" },
      );
      router.replace("/admin/assignments");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  const editable = assignment?.status !== "archived";
  const rulesEditable =
    assignment === null || assignment.status === "draft";
  const currentAudience = initialSubmissions.filter((item) => item.in_current_audience);
  const historical = initialSubmissions.filter(
    (item) => !item.in_current_audience,
  );

  const visibleAudience = currentAudience.filter((item) => matchesFilter(item, submissionFilter));

  return (
    <div className="mt-8">
      <form className="space-y-6" onSubmit={save}>
        {message ? <FormMessage tone="success">{message}</FormMessage> : null}
        {error ? <FormMessage>{error}</FormMessage> : null}

        <section className="space-y-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">内容</h2>
            <span className="font-mono text-xs text-[var(--color-text-muted)]">
              {assignment?.status ?? "new"} · revision {assignment?.revision ?? 0}
            </span>
          </div>
          <label className="block text-sm font-medium">
            标题
            <input
              className={inputClassName}
              disabled={!editable}
              maxLength={200}
              onChange={(event) => { setTitle(event.target.value); setDirty(true); }}
              required
              value={title}
            />
          </label>
          <div className="mt-4 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-soft)] sm:p-5">
            <RenderedMarkdown sanitizedHtml={assignment?.description_html ?? null} />
          </div>
          <label className="block text-sm font-medium">
            Markdown 作业说明
            <textarea
              ref={descriptionInputRef}
              className={inputClassName + " min-h-72 py-3 font-mono text-sm"}
              disabled={!editable}
              maxLength={200000}
              onChange={(event) => { setDescriptionMarkdown(event.target.value); setDirty(true); }}
              required
              value={descriptionMarkdown}
            />
            <KnowledgeReferencePicker
              disabled={!editable}
              onInsert={insertKnowledgeDocument}
            />
          </label>
          <label className="block text-sm font-medium">
            培训资料链接
            <input
              className={inputClassName}
              disabled={!editable}
              maxLength={2000}
              onChange={(event) => { setTrainingUrl(event.target.value); setDirty(true); }}
              type="url"
              value={trainingUrl}
            />
          </label>
          <label className="block text-sm font-medium">
            提交说明
            <textarea
              className={inputClassName + " min-h-32 py-3"}
              disabled={!editable}
              maxLength={50000}
              onChange={(event) => { setInstructions(event.target.value); setDirty(true); }}
              required
              value={instructions}
            />
          </label>
        </section>

        <section className="space-y-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <h2 className="text-xl font-semibold">当前作业受众</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">
            保存已发布或已关闭作业时，会按当前激活学生重新生成受众快照；正式提交历史不会删除。
          </p>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                checked={allStudents}
                disabled={!editable}
                name="assignment-audience"
                onChange={() => { setAllStudents(true); setDirty(true); }}
                type="radio"
              />
              全部激活学生
            </label>
            <label className="flex items-center gap-2">
              <input
                checked={!allStudents}
                disabled={!editable}
                name="assignment-audience"
                onChange={() => { setAllStudents(false); setDirty(true); }}
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
                        onChange={() => { setDirectionIds(toggle(directionIds, direction.id)); setDirty(true); }}
                        type="checkbox"
                      />
                      {direction.name}
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>
          ) : null}
        </section>

        <section className="grid gap-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:grid-cols-2 sm:p-6">
          <h2 className="text-xl font-semibold sm:col-span-2">提交与时间规则</h2>
          <label className="text-sm font-medium">
            允许扩展名（逗号分隔）
            <input
              className={inputClassName}
              disabled={!rulesEditable}
              onChange={(event) => { setAllowedExtensions(event.target.value); setDirty(true); }}
              value={allowedExtensions}
            />
          </label>
          <label className="text-sm font-medium">
            单版本附件总上限（字节）
            <input
              className={inputClassName}
              disabled={!rulesEditable}
              max={2147483648}
              min={1}
              onChange={(event) => { setMaxTotalBytes(event.target.value); setDirty(true); }}
              type="number"
              value={maxTotalBytes}
            />
          </label>
          <label className="text-sm font-medium">
            发布时间
            <input
              className={inputClassName}
              disabled={!rulesEditable}
              onChange={(event) => { setPublishAt(event.target.value); setDirty(true); }}
              required
              type="datetime-local"
              value={publishAt}
            />
          </label>
        </section>

        <div className="flex flex-wrap gap-3">
          <button className={buttonClassName} disabled={!editable || pending} type="submit">
            {pending ? "处理中…" : "保存"}
          </button>
          {assignment?.status === "draft" ? (
            <button
              className="min-h-11 border border-[var(--color-accent)] px-5 text-[var(--color-accent-hover)]"
              disabled={pending}
              onClick={publish}
              type="button"
            >
              发布 / 安排发布
            </button>
          ) : null}
          {assignment?.status === "published" ? (
            <button
              className="min-h-11 border border-[var(--color-danger)] px-5 text-[var(--color-danger)]"
              disabled={pending}
              onClick={close}
              type="button"
            >
              关闭作业
            </button>
          ) : null}
          {assignment && (assignment.status === "published" || assignment.status === "closed") ? (
            <button
              className="min-h-11 border border-[var(--color-border-strong)] px-5"
              disabled={pending}
              onClick={sendEmailReminder}
              type="button"
            >
              发送邮件提醒
            </button>
          ) : null}
          {assignment?.status === "closed" ? (
            <button
              className="min-h-11 border border-[var(--color-accent)] px-5 text-[var(--color-accent-hover)]"
              disabled={pending}
              onClick={reopen}
              type="button"
            >
              重新打开
            </button>
          ) : null}
          {assignment ? (
            <button
              className="min-h-11 border border-[var(--color-danger)] px-5 text-[var(--color-danger)]"
              disabled={pending}
              onClick={remove}
              type="button"
            >
              删除作业
            </button>
          ) : null}
        </div>

        {assignment && assignment.status !== "draft" ? (
          <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
            <h2 className="text-xl font-semibold">目标学生与提交</h2>
            <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
              每名学生只显示一条记录；管理员发布评语后状态变为待修改，确认当前最新版本后进入已完成。
            </p>
            <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
              {([
                ["未提交", currentAudience.filter((item) => !item.submission_id), "monitor", "text-[var(--color-text-muted)]", "unsubmitted"],
                ["已提交", currentAudience.filter((item) => item.submission_id && !item.is_completed && !item.has_feedback), "layers", "text-[var(--color-info)]", "submitted"],
                ["待修改", currentAudience.filter((item) => item.has_feedback && !item.is_completed), "mail", "text-[var(--color-warning)]", "feedback"],
                ["已完成", currentAudience.filter((item) => item.is_completed), "audit", "text-[var(--color-success)]", "completed"],
              ] as const).map(([label, matching, icon, color, filter]) => (
                <button className={`border bg-[var(--color-bg)] p-3 text-left transition ${submissionFilter === filter ? "border-[var(--color-accent)] ring-2 ring-[var(--color-accent)]/20" : "border-[var(--color-border)] hover:border-[var(--color-accent)]"}`} key={label} onClick={() => setSubmissionFilter(submissionFilter === filter ? "all" : filter)} type="button" aria-pressed={submissionFilter === filter}>
                  <div className={`flex items-center gap-2 text-xs ${color}`}><AppIcon name={icon} size={16} aria-hidden="true" />{label}</div>
                  <p className="mt-1 text-2xl font-semibold">{matching.length}</p>
                </button>
              ))}
            </div>
            <div className="mt-5 grid gap-2 border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 text-sm text-[var(--color-text-secondary)] sm:grid-cols-3">
              <p className="sm:col-span-3">发布后仍可修改标题、说明、资料链接、提交说明和受众；扩展名、附件上限和发布时间冻结。</p>
              <p>最后正式提交：{assignment.stats.last_submitted_at ? formatDateTime(assignment.stats.last_submitted_at) : "暂无"}</p>
              <p>附件上限：{formatFileSize(assignment.max_total_bytes)}</p>
            </div>
            <SubmissionStatusList items={visibleAudience} />
            {historical.length > 0 ? (
              <div className="mt-7">
                <h3 className="text-base font-semibold">历史提交（已不在当前受众）</h3>
                <SubmissionStatusList items={historical} />
              </div>
            ) : null}
          </section>
        ) : null}
      </form>

    </div>
  );
}
