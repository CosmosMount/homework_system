"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { AdminHelpRequestDetail } from "@/lib/api/types";

export function HelpRequestResolutionForm({
  initialRequest,
}: Readonly<{ initialRequest: AdminHelpRequestDetail }>) {
  const router = useRouter();
  const [revision, setRevision] = useState(initialRequest.revision);
  const [resolution, setResolution] = useState(
    initialRequest.resolution_markdown ?? "",
  );
  const [pendingAction, setPendingAction] = useState<"save" | "delete" | null>(null);
  const pending = pendingAction !== null;
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const publishesAnonymously = initialRequest.request_type === "question";

  const deleteLabel = publishesAnonymously ? "删除问题答疑" : "删除系统反馈";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPendingAction("save");
    setError(null);
    setSuccess(null);
    try {
      const updated = await csrfFetch<AdminHelpRequestDetail>(
        "/admin/help-requests/" +
          encodeURIComponent(initialRequest.id) +
          "/resolution",
        {
          method: "PUT",
          body: JSON.stringify({
            resolution_markdown: resolution,
            revision,
          }),
        },
      );
      setRevision(updated.revision);
      setResolution(updated.resolution_markdown ?? "");
      setSuccess(
        initialRequest.status === "resolved"
          ? publishesAnonymously
            ? "答复修订已保存，公开答疑已更新，学生已收到新的站内提醒。"
            : "处理结果修订已保存，学生已收到新的站内提醒。"
          : publishesAnonymously
            ? "答复已保存并匿名公开，学生已收到站内提醒。"
            : "处理结果已保存，学生已收到站内提醒。",
      );
      router.refresh();
    } catch (nextError) {
      setError(
        nextError instanceof ApiError
          ? nextError.code === "REVISION_CONFLICT"
            ? "该记录已被更新，请刷新页面后再提交。"
            : nextError.message
          : "保存答复失败，请稍后重试。",
      );
    } finally {
      setPendingAction(null);
    }
  }

  async function remove() {
    const prompt = publishesAnonymously
      ? "确认永久删除这条问题答疑？删除后将从学生本人记录和匿名公开答疑移除，且无法由应用恢复。"
      : "确认永久删除这条系统反馈？删除后将从学生本人记录移除，且无法由应用恢复。";
    if (!window.confirm(prompt)) return;
    setPendingAction("delete");
    setError(null);
    setSuccess(null);
    try {
      await csrfFetch(
        "/admin/help-requests/" + encodeURIComponent(initialRequest.id),
        { method: "DELETE" },
      );
      router.replace("/admin/help");
    } catch (nextError) {
      setError(
        nextError instanceof ApiError
          ? nextError.message
          : "删除反馈答疑失败，请稍后重试。",
      );
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <form
      className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6"
      onSubmit={submit}
    >
      <h2 className="text-xl font-semibold">
        {initialRequest.status === "resolved" ? "修订处理结果" : "填写处理结果"}
      </h2>
      <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
        {publishesAnonymously
          ? "问题答疑保存后会向所有登录用户匿名公开，并向提问学生发送不含正文的站内提醒。"
          : "系统反馈始终仅提问学生和管理员可见；保存后学生会收到不含正文的站内提醒。"}
      </p>

      <div className="mt-5">
        <label className="block text-sm font-medium" htmlFor="help-resolution">
          处理结果或答复
        </label>
        <textarea
          className={inputClassName + " min-h-56 py-3"}
          id="help-resolution"
          maxLength={20000}
          onChange={(event) => setResolution(event.target.value)}
          placeholder="可以使用 Markdown 填写解决方案或问题答复。"
          required
          value={resolution}
        />
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">
          {resolution.length}/20000 · 当前版本 {revision}
        </p>
      </div>

      <div className="mt-5 space-y-4">
        {error ? <FormMessage>{error}</FormMessage> : null}
        {success ? <FormMessage tone="success">{success}</FormMessage> : null}
        <button
          className={buttonClassName}
          disabled={pending || resolution.trim().length === 0}
          type="submit"
        >
          {pendingAction === "save" ? "保存中…" : "保存并通知学生"}
        </button>
        <div className="border-t border-[var(--color-border)] pt-4">
          <p className="mb-3 text-sm text-[var(--color-text-secondary)]">
            删除后，工单会立即从学生本人记录
            {publishesAnonymously ? "和匿名公开答疑" : ""}
            中移除，且无法由应用恢复；脱敏审计记录仍会保留。
          </p>
          <button
            className="min-h-11 border border-[var(--color-danger)] px-5 text-[var(--color-danger)] disabled:opacity-55"
            disabled={pending}
            onClick={remove}
            type="button"
          >
            {pendingAction === "delete" ? "删除中…" : deleteLabel}
          </button>
        </div>
      </div>
    </form>
  );
}
