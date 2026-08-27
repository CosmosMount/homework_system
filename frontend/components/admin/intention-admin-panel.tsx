"use client";

import Image from "next/image";
import { type FormEvent, useState } from "react";
import QRCode from "qrcode";

import {
  buttonClassName,
  commandButtonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, apiFetch, csrfFetch } from "@/lib/api/client";
import type {
  AdminIntentionSurvey,
  IntentionQr,
  IntentionStats,
  IntentionStatus,
} from "@/lib/api/types";

const defaultOptions = "机器人\n视觉\n嵌入式";

const statusLabels: Record<IntentionStatus, string> = {
  draft: "草稿",
  open: "开放中",
  closed: "已关闭",
  archived: "已归档",
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function IntentionAdminPanel({
  initialSurveys,
}: Readonly<{ initialSurveys: AdminIntentionSurvey[] }>) {
  const [surveys, setSurveys] = useState(initialSurveys);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [options, setOptions] = useState(defaultOptions);
  const [allowMultiple, setAllowMultiple] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<Record<string, IntentionStats>>({});
  const [qr, setQr] = useState<
    Record<string, { url: string; image: string }>
  >({});

  function begin() {
    setPending(true);
    setError(null);
    setMessage(null);
  }

  async function createSurvey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const labels = options
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    if (!title.trim() || labels.length === 0) {
      setError("标题和至少一个选项不能为空。");
      return;
    }

    begin();
    try {
      const created = await csrfFetch<AdminIntentionSurvey>(
        "/admin/intentions",
        {
          method: "POST",
          body: JSON.stringify({
            title: title.trim(),
            description_markdown: description,
            options: labels.map((label) => ({ label })),
            allow_multiple: allowMultiple,
          }),
        },
      );
      setSurveys((current) => [created, ...current]);
      setTitle("");
      setDescription("");
      setOptions(defaultOptions);
      setAllowMultiple(false);
      setMessage("调查已创建。开放填写后学生即可提交意向。");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function transition(
    survey: AdminIntentionSurvey,
    action: "open" | "closed" | "archived",
  ) {
    begin();
    try {
      const updated = await csrfFetch<AdminIntentionSurvey>(
        "/admin/intentions/" + survey.id + "/" + action,
        { method: "POST" },
      );
      setSurveys((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      if (action !== "open") {
        setQr((current) => {
          const next = { ...current };
          delete next[survey.id];
          return next;
        });
      }
      setMessage("调查状态已更新为“" + statusLabels[updated.status] + "”。");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function loadStats(surveyId: string) {
    begin();
    try {
      const result = await apiFetch<IntentionStats>(
        "/admin/intentions/" + surveyId + "/stats",
      );
      setStats((current) => ({ ...current, [surveyId]: result }));
      setSurveys((current) =>
        current.map((item) =>
          item.id === surveyId
            ? { ...item, responded_count: result.responded_count }
            : item,
        ),
      );
      setMessage("统计数据已刷新。");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function generateQr(surveyId: string) {
    begin();
    try {
      const result = await csrfFetch<IntentionQr>(
        "/admin/intentions/" + surveyId + "/qr-token",
        { method: "POST" },
      );
      const image = await QRCode.toDataURL(result.fill_url, {
        width: 280,
        margin: 2,
        errorCorrectionLevel: "M",
      });
      setQr((current) => ({
        ...current,
        [surveyId]: { url: result.fill_url, image },
      }));
      setMessage("二维码已生成；学生扫码后仍需使用本人账号登录。");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-8 space-y-8">
      {message ? <FormMessage tone="success">{message}</FormMessage> : null}
      {error ? <FormMessage>{error}</FormMessage> : null}

      <form
        className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6"
        onSubmit={createSurvey}
      >
        <h2 className="text-xl font-semibold">新建意向调查</h2>
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <label className="block text-sm font-medium">
            标题
            <input
              className={inputClassName}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
              required
              value={title}
            />
          </label>
          <label className="block text-sm font-medium">
            选项（每行一个）
            <textarea
              className={inputClassName + " min-h-32 py-3"}
              maxLength={6_000}
              onChange={(event) => setOptions(event.target.value)}
              required
              value={options}
            />
          </label>
          <label className="block text-sm font-medium lg:col-span-2">
            说明（Markdown，可选）
            <textarea
              className={inputClassName + " min-h-28 py-3"}
              maxLength={100_000}
              onChange={(event) => setDescription(event.target.value)}
              value={description}
            />
          </label>
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input
            checked={allowMultiple}
            className="size-4 accent-[var(--color-accent)]"
            onChange={(event) => setAllowMultiple(event.target.checked)}
            type="checkbox"
          />
          允许学生多选
        </label>
        <button
          className={buttonClassName + " mt-5 w-full sm:w-auto"}
          disabled={pending}
          type="submit"
        >
          {pending ? "处理中…" : "创建调查"}
        </button>
      </form>

      <section aria-label="意向调查列表" className="space-y-4">
        {surveys.map((survey) => {
          const surveyStats = stats[survey.id];
          const surveyQr = qr[survey.id];
          const qrAvailable =
            survey.status === "draft" || survey.status === "open";
          return (
            <article
              className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6"
              key={survey.id}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold">{survey.title}</h2>
                  <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                    {survey.allow_multiple ? "多选" : "单选"} ·{" "}
                    {survey.option_count} 个选项 · {survey.responded_count} 人已填写
                  </p>
                </div>
                <span className="rounded-full bg-[var(--color-action-fill)] px-3 py-1 text-xs text-[var(--color-action-text)]">
                  {statusLabels[survey.status]}
                </span>
              </div>

              <div className="mt-5 flex flex-wrap gap-2">
                {survey.status === "draft" ? (
                  <button
                    className={commandButtonClassName}
                    disabled={pending}
                    onClick={() => transition(survey, "open")}
                    type="button"
                  >
                    开放填写
                  </button>
                ) : null}
                {survey.status === "open" ? (
                  <button
                    className={commandButtonClassName}
                    disabled={pending}
                    onClick={() => transition(survey, "closed")}
                    type="button"
                  >
                    关闭调查
                  </button>
                ) : null}
                {survey.status === "closed" ? (
                  <button
                    className={commandButtonClassName}
                    disabled={pending}
                    onClick={() => transition(survey, "archived")}
                    type="button"
                  >
                    归档调查
                  </button>
                ) : null}
                {qrAvailable ? (
                  <button
                    className={commandButtonClassName}
                    disabled={pending}
                    onClick={() => generateQr(survey.id)}
                    type="button"
                  >
                    生成二维码
                  </button>
                ) : null}
                <button
                  className={commandButtonClassName}
                  disabled={pending}
                  onClick={() => loadStats(survey.id)}
                  type="button"
                >
                  查看统计
                </button>
              </div>

              {surveyQr ? (
                <div className="mt-5 flex flex-col items-start gap-5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 sm:flex-row sm:items-center">
                  <Image
                    alt={survey.title + "移动端填写二维码"}
                    className="h-auto w-56 max-w-full rounded-lg bg-white p-2"
                    height={224}
                    src={surveyQr.image}
                    unoptimized
                    width={224}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">移动端填写地址</p>
                    <p className="mt-2 break-all text-xs text-[var(--color-text-muted)]">
                      {surveyQr.url}
                    </p>
                    <a
                      className="mt-3 inline-flex text-sm text-[var(--color-info)] underline underline-offset-4"
                      href={surveyQr.url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      打开填写页
                    </a>
                    <p className="mt-3 text-xs text-[var(--color-text-secondary)]">
                      二维码 token 只保存哈希，重新生成会立即使旧码失效；扫码后仍须登录。
                    </p>
                  </div>
                </div>
              ) : null}

              {surveyStats ? (
                <div className="mt-5 rounded-xl border border-[var(--color-border)] p-4">
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    填写率 {surveyStats.response_rate}%（
                    {surveyStats.responded_count} /{" "}
                    {surveyStats.total_active_students}）
                  </p>
                  <div className="mt-4 space-y-3">
                    {surveyStats.options.map((option) => (
                      <div key={option.option_id}>
                        <div className="flex justify-between gap-4 text-sm">
                          <span>{option.label}</span>
                          <span className="font-mono text-[var(--color-text-muted)]">
                            {option.response_count} · {option.percentage}%
                          </span>
                        </div>
                        <div
                          aria-label={option.label + "选择比例"}
                          aria-valuemax={100}
                          aria-valuemin={0}
                          aria-valuenow={Math.min(option.percentage, 100)}
                          className="mt-1 h-2 rounded-full bg-[var(--color-surface-hover)]"
                          role="progressbar"
                        >
                          <div
                            className="h-2 rounded-full bg-[var(--color-accent-fill)]"
                            style={{
                              width: Math.min(option.percentage, 100) + "%",
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </article>
          );
        })}
        {surveys.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[var(--color-border-strong)] p-8 text-center text-sm text-[var(--color-text-muted)]">
            还没有意向调查。
          </p>
        ) : null}
      </section>
    </div>
  );
}
