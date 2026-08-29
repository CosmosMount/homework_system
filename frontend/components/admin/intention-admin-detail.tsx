"use client";

import { type FormEvent, useState } from "react";

import {
  buttonClassName,
  commandButtonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, apiFetch, csrfFetch } from "@/lib/api/client";
import type {
  AdminIntentionSurvey,
  AdminIntentionSurveyDetail,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

let nextEditQuestionId = 1;

type QuestionDraft = {
  key: string;
  prompt: string;
  options: string;
  allowMultiple: boolean;
};

type EditDraft = {
  revision: number;
  title: string;
  description: string;
  maxSubmissions: string;
  startsAt: string;
  endsAt: string;
  questions: QuestionDraft[];
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

function toLocalDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function questionDrafts(detail: AdminIntentionSurveyDetail): QuestionDraft[] {
  return detail.questions.map((question) => ({
    key: question.id,
    prompt: question.prompt,
    options: question.options.map((option) => option.label).join("\n"),
    allowMultiple: question.allow_multiple,
  }));
}

function makeEditDraft(detail: AdminIntentionSurveyDetail): EditDraft {
  return {
    revision: detail.revision,
    title: detail.title,
    description: detail.description_markdown,
    maxSubmissions:
      detail.max_submissions === null ? "" : String(detail.max_submissions),
    startsAt: toLocalDateTime(detail.starts_at),
    endsAt: toLocalDateTime(detail.ends_at),
    questions: questionDrafts(detail),
  };
}

export function IntentionAdminDetail({
  disabled,
  onUpdated,
  survey,
}: Readonly<{
  disabled: boolean;
  onUpdated: (survey: AdminIntentionSurveyDetail) => void;
  survey: AdminIntentionSurvey;
}>) {
  const [detail, setDetail] = useState<AdminIntentionSurveyDetail | null>(null);
  const [edit, setEdit] = useState<EditDraft | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function begin() {
    setPending(true);
    setMessage(null);
    setError(null);
  }

  async function fetchDetail(): Promise<AdminIntentionSurveyDetail> {
    const result = await apiFetch<AdminIntentionSurveyDetail>(
      "/admin/intentions/" + survey.id,
    );
    setDetail(result);
    return result;
  }

  async function loadDetail() {
    begin();
    try {
      await fetchDetail();
      setMessage("问卷内容已加载。");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function beginEdit() {
    begin();
    try {
      const current = detail ?? (await fetchDetail());
      setEdit(makeEditDraft(current));
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  function updateQuestion(key: string, patch: Partial<QuestionDraft>) {
    setEdit((current) =>
      current
        ? {
            ...current,
            questions: current.questions.map((question) =>
              question.key === key ? { ...question, ...patch } : question,
            ),
          }
        : current,
    );
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!edit) return;
    const questions = edit.questions.map((question) => ({
      prompt: question.prompt.trim(),
      allow_multiple: question.allowMultiple,
      options: question.options
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean)
        .map((label) => ({ label })),
    }));
    if (
      !edit.title.trim() ||
      questions.length === 0 ||
      questions.some((question) => !question.prompt || question.options.length === 0)
    ) {
      setError("问卷标题、每道题目和每题至少一个选项不能为空。");
      return;
    }
    const maxSubmissions = edit.maxSubmissions.trim()
      ? Number(edit.maxSubmissions)
      : null;
    if (
      maxSubmissions !== null &&
      (!Number.isInteger(maxSubmissions) || maxSubmissions < 1 || maxSubmissions > 100)
    ) {
      setError("最多提交次数必须是 1～100 的整数，留空表示不限次数。");
      return;
    }

    begin();
    try {
      const updated = await csrfFetch<AdminIntentionSurveyDetail>(
        "/admin/intentions/" + survey.id,
        {
          method: "PATCH",
          body: JSON.stringify({
            revision: edit.revision,
            title: edit.title.trim(),
            description_markdown: edit.description,
            questions,
            max_submissions: maxSubmissions,
            starts_at: edit.startsAt ? new Date(edit.startsAt).toISOString() : null,
            ends_at: edit.endsAt ? new Date(edit.endsAt).toISOString() : null,
          }),
        },
      );
      setDetail(updated);
      setEdit(null);
      onUpdated(updated);
      setMessage("问卷修改已保存。");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  const busy = disabled || pending;

  return (
    <div className="mt-5">
      <div className="flex flex-wrap gap-2">
        <button
          className={commandButtonClassName}
          disabled={busy}
          onClick={loadDetail}
          type="button"
        >
          {detail ? "刷新内容" : "查看内容"}
        </button>
        {survey.status === "draft" ? (
          <button
            className={commandButtonClassName}
            disabled={busy}
            onClick={beginEdit}
            type="button"
          >
            编辑问卷
          </button>
        ) : null}
      </div>

      {message ? <div className="mt-3"><FormMessage tone="success">{message}</FormMessage></div> : null}
      {error ? <div className="mt-3"><FormMessage>{error}</FormMessage></div> : null}

      {edit && survey.status === "draft" ? (
        <form
          className="mt-5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 sm:p-5"
          onSubmit={saveEdit}
        >
          <h3 className="text-base font-semibold">编辑问卷</h3>
          <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
            仅草稿允许修改；保存会整体替换题目与选项。
          </p>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <label className="block text-sm font-medium">
              编辑问卷标题
              <input
                className={inputClassName}
                maxLength={200}
                onChange={(event) => setEdit({ ...edit, title: event.target.value })}
                required
                value={edit.title}
              />
            </label>
            <label className="block text-sm font-medium">
              编辑每人最多提交次数
              <input
                className={inputClassName}
                max={100}
                min={1}
                onChange={(event) =>
                  setEdit({ ...edit, maxSubmissions: event.target.value })
                }
                placeholder="留空表示不限次数"
                type="number"
                value={edit.maxSubmissions}
              />
            </label>
            <label className="block text-sm font-medium">
              开始时间（可选）
              <input
                className={inputClassName}
                onChange={(event) => setEdit({ ...edit, startsAt: event.target.value })}
                type="datetime-local"
                value={edit.startsAt}
              />
            </label>
            <label className="block text-sm font-medium">
              结束时间（可选）
              <input
                className={inputClassName}
                onChange={(event) => setEdit({ ...edit, endsAt: event.target.value })}
                type="datetime-local"
                value={edit.endsAt}
              />
            </label>
            <label className="block text-sm font-medium lg:col-span-2">
              编辑说明（Markdown，可选）
              <textarea
                className={inputClassName + " min-h-28 py-3"}
                maxLength={100_000}
                onChange={(event) =>
                  setEdit({ ...edit, description: event.target.value })
                }
                value={edit.description}
              />
            </label>
          </div>

          <div className="mt-5 space-y-4">
            {edit.questions.map((question, index) => (
              <fieldset
                className="rounded-xl border border-[var(--color-border)] p-4"
                key={question.key}
              >
                <legend className="px-2 text-sm font-semibold">
                  编辑第 {index + 1} 题
                </legend>
                <div className="grid gap-4 lg:grid-cols-2">
                  <label className="block text-sm font-medium">
                    题目
                    <input
                      aria-label={"编辑题目 " + (index + 1)}
                      className={inputClassName}
                      maxLength={200}
                      onChange={(event) =>
                        updateQuestion(question.key, { prompt: event.target.value })
                      }
                      required
                      value={question.prompt}
                    />
                  </label>
                  <label className="block text-sm font-medium">
                    选项（每行一个）
                    <textarea
                      aria-label={"编辑选项 " + (index + 1)}
                      className={inputClassName + " min-h-28 py-3"}
                      maxLength={6_000}
                      onChange={(event) =>
                        updateQuestion(question.key, { options: event.target.value })
                      }
                      required
                      value={question.options}
                    />
                  </label>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      aria-label={"编辑第 " + (index + 1) + " 题允许多选"}
                      checked={question.allowMultiple}
                      className="size-4 accent-[var(--color-accent)]"
                      onChange={(event) =>
                        updateQuestion(question.key, {
                          allowMultiple: event.target.checked,
                        })
                      }
                      type="checkbox"
                    />
                    本题允许多选
                  </label>
                  {edit.questions.length > 1 ? (
                    <button
                      className={commandButtonClassName}
                      onClick={() =>
                        setEdit({
                          ...edit,
                          questions: edit.questions.filter(
                            (item) => item.key !== question.key,
                          ),
                        })
                      }
                      type="button"
                    >
                      删除本题
                    </button>
                  ) : null}
                </div>
              </fieldset>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              className={commandButtonClassName}
              disabled={edit.questions.length >= 30}
              onClick={() =>
                setEdit({
                  ...edit,
                  questions: [
                    ...edit.questions,
                    {
                      key: "new-" + nextEditQuestionId++,
                      prompt: "第 " + (edit.questions.length + 1) + " 志愿",
                      options: "",
                      allowMultiple: false,
                    },
                  ],
                })
              }
              type="button"
            >
              添加题目
            </button>
            <button className={buttonClassName} disabled={busy} type="submit">
              {pending ? "保存中…" : "保存修改"}
            </button>
            <button
              className={commandButtonClassName}
              disabled={busy}
              onClick={() => setEdit(null)}
              type="button"
            >
              取消编辑
            </button>
          </div>
        </form>
      ) : null}

      {detail && (!edit || survey.status !== "draft") ? (
        <section
          aria-label={detail.title + "问卷内容"}
          className="mt-5 rounded-xl border border-[var(--color-border)] p-4 sm:p-5"
        >
          <h3 className="text-base font-semibold">问卷内容</h3>
          <dl className="mt-3 grid gap-2 text-sm text-[var(--color-text-secondary)] sm:grid-cols-2">
            <div><dt className="inline font-medium">开始时间：</dt><dd className="inline">{detail.starts_at ? formatDateTime(detail.starts_at) : "立即"}</dd></div>
            <div><dt className="inline font-medium">结束时间：</dt><dd className="inline">{detail.ends_at ? formatDateTime(detail.ends_at) : "不限"}</dd></div>
            <div><dt className="inline font-medium">提交限制：</dt><dd className="inline">{detail.max_submissions === null ? "不限次数" : "每人最多 " + detail.max_submissions + " 次"}</dd></div>
            <div><dt className="inline font-medium">当前版本：</dt><dd className="inline">{detail.revision}</dd></div>
          </dl>
          <div className="mt-4">
            <p className="text-sm font-medium">说明（Markdown）</p>
            <pre className="mt-2 whitespace-pre-wrap break-words rounded-lg bg-[var(--color-surface-raised)] p-3 font-sans text-sm text-[var(--color-text-secondary)]">
              {detail.description_markdown || "无说明"}
            </pre>
          </div>
          <ol className="mt-4 space-y-4">
            {detail.questions.map((question, index) => (
              <li
                className="rounded-lg bg-[var(--color-surface-raised)] p-4"
                key={question.id}
              >
                <p className="text-sm font-semibold">
                  {index + 1}. {question.prompt}（{question.allow_multiple ? "多选" : "单选"}）
                </p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[var(--color-text-secondary)]">
                  {question.options.map((option) => (
                    <li key={option.id}>{option.label}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
          {survey.status !== "draft" ? (
            <p className="mt-4 text-xs text-[var(--color-text-muted)]">
              已开放、关闭或归档的问卷只能查看，题目结构不可修改。
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
