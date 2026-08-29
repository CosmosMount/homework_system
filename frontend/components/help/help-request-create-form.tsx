"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type {
  HelpRequestDetail,
  HelpRequestType,
} from "@/lib/api/types";

export function HelpRequestCreateForm() {
  const router = useRouter();
  const [requestType, setRequestType] =
    useState<HelpRequestType>("system_feedback");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const created = await csrfFetch<HelpRequestDetail>("/help-requests", {
        method: "POST",
        body: JSON.stringify({
          request_type: requestType,
          title,
          content_markdown: content,
        }),
      });
      router.push("/help/" + created.id);
      router.refresh();
    } catch (nextError) {
      setError(
        nextError instanceof ApiError
          ? nextError.message
          : "提交失败，请稍后重试。",
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
      <div>
        <p className="font-mono text-xs tracking-[0.14em] text-[var(--color-accent)]">
          NEW REQUEST
        </p>
        <h2 className="mt-2 text-xl font-semibold">提交反馈或问题</h2>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
          {requestType === "question"
            ? "问题解答前仅本人和管理员可见，管理员解答后将匿名公开。"
            : "系统反馈始终仅本人和管理员可见。"}{" "}
          请勿填写密码、Cookie 或其他账号秘密。
        </p>
      </div>

      <div className="mt-6 space-y-5">
        <div>
          <label className="block text-sm font-medium" htmlFor="help-request-type">
            类型
          </label>
          <select
            className={inputClassName}
            id="help-request-type"
            onChange={(event) =>
              setRequestType(event.target.value as HelpRequestType)
            }
            value={requestType}
          >
            <option value="system_feedback">系统反馈</option>
            <option value="question">问题答疑</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium" htmlFor="help-request-title">
            标题
          </label>
          <input
            className={inputClassName}
            id="help-request-title"
            maxLength={200}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="简要概括反馈或问题"
            required
            value={title}
          />
          <p className="mt-2 text-xs text-[var(--color-text-muted)]">
            {title.length}/200
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium" htmlFor="help-request-content">
            详情
          </label>
          <textarea
            className={inputClassName + " min-h-48 py-3"}
            id="help-request-content"
            maxLength={20000}
            onChange={(event) => setContent(event.target.value)}
            placeholder="可以使用 Markdown 描述现象、复现步骤或具体问题。"
            required
            value={content}
          />
          <p className="mt-2 text-xs text-[var(--color-text-muted)]">
            {content.length}/20000
          </p>
        </div>

        {error ? <FormMessage>{error}</FormMessage> : null}

        <button
          className={buttonClassName}
          disabled={
            pending || title.trim().length === 0 || content.trim().length === 0
          }
          type="submit"
        >
          {pending ? "提交中…" : "提交反馈答疑"}
        </button>
      </div>
    </form>
  );
}
