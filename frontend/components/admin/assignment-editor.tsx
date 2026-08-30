"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { RenderedMarkdown } from "@/components/announcements/safe-html";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type {
  AssignmentAdmin,
  AssignmentExtension,
  AssignmentSubmissionAdminItem,
  Direction,
} from "@/lib/api/types";
import { formatDateTime, formatFileSize } from "@/lib/format";
import { createIdempotencyKey } from "@/lib/idempotency";

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

function ExtensionControls({
  assignmentId,
  userId,
}: Readonly<{ assignmentId: string; userId: string }>) {
  const [deadline, setDeadline] = useState("");
  const [reason, setReason] = useState("");
  const [saved, setSaved] = useState<AssignmentExtension | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function grant() {
    if (!deadline || !reason.trim()) {
      setMessage("延期时间和理由不能为空。");
      return;
    }
    setPending(true);
    setMessage(null);
    try {
      const result = await csrfFetch<AssignmentExtension>(
        "/admin/assignments/" +
          assignmentId +
          "/extensions/" +
          userId,
        {
          method: "PUT",
          body: JSON.stringify({
            extended_deadline: apiDateTime(deadline),
            reason: reason.trim(),
          }),
        },
      );
      setSaved(result);
      setMessage("个人延期已保存并进入提醒队列。");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setPending(false);
    }
  }

  async function remove() {
    if (!window.confirm("确认移除个人延期？截止后使用过的延期不能移除。")) {
      return;
    }
    setPending(true);
    setMessage(null);
    try {
      await csrfFetch(
        "/admin/assignments/" +
          assignmentId +
          "/extensions/" +
          userId,
        { method: "DELETE" },
      );
      setSaved(null);
      setDeadline("");
      setReason("");
      setMessage("个人延期已移除。");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-sm text-[var(--color-info)]">
        管理个人延期
      </summary>
      <div className="mt-3 grid gap-3 border border-[var(--color-border)] p-3 md:grid-cols-2">
        <label className="text-xs">
          延期至
          <input
            className={inputClassName}
            disabled={pending}
            onChange={(event) => setDeadline(event.target.value)}
            type="datetime-local"
            value={deadline}
          />
        </label>
        <label className="text-xs">
          内部理由
          <input
            className={inputClassName}
            disabled={pending}
            maxLength={2000}
            onChange={(event) => setReason(event.target.value)}
            value={reason}
          />
        </label>
        <div className="flex flex-wrap gap-2 md:col-span-2">
          <button
            className={buttonClassName + " px-4 text-sm disabled:opacity-55"}
            disabled={pending}
            onClick={grant}
            type="button"
          >
            保存延期
          </button>
          {saved ? (
            <button
              className="min-h-10 border border-[var(--color-danger)] px-4 text-sm text-[var(--color-danger)]"
              disabled={pending}
              onClick={remove}
              type="button"
            >
              移除延期
            </button>
          ) : null}
        </div>
        {message ? (
          <p
            aria-live="polite"
            className="text-xs text-[var(--color-text-muted)] md:col-span-2"
          >
            {message}
          </p>
        ) : null}
      </div>
    </details>
  );
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
  const [assignment, setAssignment] = useState(initialAssignment);
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
  const [deadline, setDeadline] = useState(
    localDateTime(
      initialAssignment?.deadline ??
        new Date(new Date(publishAt).getTime() + 7 * 24 * 60 * 60 * 1000).toISOString(),
    ),
  );
  const [pending, setPending] = useState(false);
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
    if (!publishAt || !deadline || new Date(deadline) <= new Date(publishAt)) {
      setError("截止时间必须晚于发布时间。");
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
      allowed_extensions: extensionList(),
      max_total_bytes: Number(maxTotalBytes),
      publish_at: apiDateTime(publishAt),
      deadline: apiDateTime(deadline),
    };
  }

  async function persist(): Promise<AssignmentAdmin> {
    if (!validate()) throw new Error("FORM_INVALID");
    const current = assignment;
    const saved = await csrfFetch<AssignmentAdmin>(
      current === null
        ? "/admin/assignments"
        : "/admin/assignments/" + current.id,
      {
        method: current === null ? "POST" : "PATCH",
        body: JSON.stringify(payload(current?.revision)),
      },
    );
    setAssignment(saved);
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
      await persist();
      setMessage("作业草稿已保存。");
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
      const result = await csrfFetch<AssignmentAdmin>(
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
    if (!window.confirm("确认提前关闭？这会覆盖所有个人延期。")) return;
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const result = await csrfFetch<AssignmentAdmin>(
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
      await csrfFetch(
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
  const configurationEditable =
    assignment === null || assignment.status === "draft";

  return (
    <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
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
              onChange={(event) => setTitle(event.target.value)}
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
              className={inputClassName + " min-h-72 py-3 font-mono text-sm"}
              disabled={!editable}
              maxLength={200000}
              onChange={(event) => setDescriptionMarkdown(event.target.value)}
              required
              value={descriptionMarkdown}
            />
          </label>
          <label className="block text-sm font-medium">
            培训资料链接
            <input
              className={inputClassName}
              disabled={!editable}
              maxLength={2000}
              onChange={(event) => setTrainingUrl(event.target.value)}
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
              onChange={(event) => setInstructions(event.target.value)}
              required
              value={instructions}
            />
          </label>
        </section>

        <section className="space-y-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <h2 className="text-xl font-semibold">受众快照配置</h2>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                checked={allStudents}
                disabled={!configurationEditable}
                name="assignment-audience"
                onChange={() => setAllStudents(true)}
                type="radio"
              />
              全部激活学生
            </label>
            <label className="flex items-center gap-2">
              <input
                checked={!allStudents}
                disabled={!configurationEditable}
                name="assignment-audience"
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
                        disabled={!configurationEditable || !direction.is_active}
                        onChange={() =>
                          setDirectionIds(toggle(directionIds, direction.id))
                        }
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
              disabled={!configurationEditable}
              onChange={(event) => setAllowedExtensions(event.target.value)}
              value={allowedExtensions}
            />
          </label>
          <label className="text-sm font-medium">
            单版本附件总上限（字节）
            <input
              className={inputClassName}
              disabled={!configurationEditable}
              max={2147483648}
              min={1}
              onChange={(event) => setMaxTotalBytes(event.target.value)}
              type="number"
              value={maxTotalBytes}
            />
          </label>
          <label className="text-sm font-medium">
            发布时间
            <input
              className={inputClassName}
              disabled={!configurationEditable}
              onChange={(event) => setPublishAt(event.target.value)}
              required
              type="datetime-local"
              value={publishAt}
            />
          </label>
          <label className="text-sm font-medium">
            公共截止
            <input
              className={inputClassName}
              disabled={!editable}
              onChange={(event) => setDeadline(event.target.value)}
              required
              type="datetime-local"
              value={deadline}
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
              提前关闭
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
            <div className="mt-4 space-y-3">
              {initialSubmissions.map((item) => (
                <article
                  className="border border-[var(--color-border)] p-4"
                  key={item.user_id}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{item.full_name}</p>
                      <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                        {item.student_number}
                      </p>
                    </div>
                    {item.submission_id ? (
                      <Link
                        className="text-sm text-[var(--color-info)]"
                        href={"/admin/submissions/" + item.submission_id}
                      >
                        查看 v{item.latest_version_number} →
                      </Link>
                    ) : (
                      <span className="text-sm text-[var(--color-text-muted)]">
                        未提交
                      </span>
                    )}
                  </div>
                  <ExtensionControls
                    assignmentId={assignment.id}
                    userId={item.user_id}
                  />
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </form>

      <aside className="space-y-4">
        <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-lg font-semibold">统计</h2>
          <dl className="mt-4 space-y-3 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-[var(--color-text-muted)]">预计 / 实际受众</dt>
              <dd>
                {assignment?.estimated_recipient_count ?? 0} /{" "}
                {assignment?.actual_recipient_count ?? 0}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-[var(--color-text-muted)]">已提交</dt>
              <dd>{assignment?.stats.submitted_count ?? 0}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-[var(--color-text-muted)]">未提交</dt>
              <dd>{assignment?.stats.unsubmitted_count ?? 0}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-[var(--color-text-muted)]">已有评语</dt>
              <dd>{assignment?.stats.feedback_submission_count ?? 0}</dd>
            </div>
          </dl>
        </section>
        <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 text-sm text-[var(--color-text-secondary)]">
          <p>发布后受众、扩展名、附件上限和发布时间冻结。</p>
          <p className="mt-3">
            当前截止：{assignment ? formatDateTime(assignment.deadline) : "—"}
          </p>
          <p className="mt-2">
            附件上限：{assignment ? formatFileSize(assignment.max_total_bytes) : "—"}
          </p>
        </section>
      </aside>
    </div>
  );
}
