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
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const publishesAnonymously = initialRequest.request_type === "question";


  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
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
      setPending(false);
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
          {pending ? "保存中…" : "保存并通知学生"}
        </button>
      </div>
    </form>
  );
}
