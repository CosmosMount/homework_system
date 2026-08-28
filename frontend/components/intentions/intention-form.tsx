"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { IntentionSurvey } from "@/lib/api/types";

type SavedResponse = NonNullable<IntentionSurvey["response"]>;

export function IntentionForm({
  initialSurvey,
}: Readonly<{ initialSurvey: IntentionSurvey }>) {
  const router = useRouter();
  const initialAnswers = Object.fromEntries(
    initialSurvey.questions.map((question) => [
      question.id,
      initialSurvey.response?.answers.find(
        (answer) => answer.question_id === question.id,
      )?.selected_option_ids ?? [],
    ]),
  );
  const [answers, setAnswers] = useState<Record<string, string[]>>(
    initialAnswers,
  );
  const [freeText, setFreeText] = useState(
    initialSurvey.response?.free_text ?? "",
  );
  const [submissionCount, setSubmissionCount] = useState(
    initialSurvey.submissions_used,
  );
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const limitReached =
    initialSurvey.max_submissions !== null &&
    submissionCount >= initialSurvey.max_submissions;

  function toggle(
    questionId: string,
    optionId: string,
    allowMultiple: boolean,
  ) {
    setAnswers((current) => {
      const selected = current[questionId] ?? [];
      return {
        ...current,
        [questionId]: allowMultiple
          ? selected.includes(optionId)
            ? selected.filter((item) => item !== optionId)
            : [...selected, optionId]
          : [optionId],
      };
    });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (limitReached) {
      setError("已达到该问卷允许的提交次数。");
      return;
    }
    if (
      initialSurvey.questions.some(
        (question) => (answers[question.id] ?? []).length === 0,
      )
    ) {
      setError("请完成问卷中的全部题目。");
      return;
    }

    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const result = await csrfFetch<SavedResponse>(
        "/intentions/" + initialSurvey.id + "/response",
        {
          method: "PUT",
          body: JSON.stringify({
            answers: initialSurvey.questions.map((question) => ({
              question_id: question.id,
              selected_option_ids: answers[question.id],
            })),
            free_text: freeText.trim() || null,
          }),
        },
      );
      setSubmissionCount(result.submission_count);
      const remaining =
        initialSurvey.max_submissions === null
          ? null
          : initialSurvey.max_submissions - result.submission_count;
      setMessage(
        remaining === null
          ? "问卷已保存，开放期间可以继续提交。"
          : remaining > 0
            ? "问卷已保存，还可提交 " + remaining + " 次。"
            : "问卷已保存，提交次数已经用完。",
      );
      router.refresh();
    } catch (nextError) {
      setError(
        nextError instanceof ApiError
          ? nextError.message
          : "保存失败，请稍后重试。",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6"
      onSubmit={save}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">填写问卷</h2>
        <span className="text-sm text-[var(--color-text-muted)]">
          已提交 {submissionCount} 次 ·{" "}
          {initialSurvey.max_submissions === null
            ? "不限次数"
            : "最多 " + initialSurvey.max_submissions + " 次"}
        </span>
      </div>
      {message ? (
        <div className="mt-4">
          <FormMessage tone="success">{message}</FormMessage>
        </div>
      ) : null}
      {error ? (
        <div className="mt-4">
          <FormMessage>{error}</FormMessage>
        </div>
      ) : null}
      {limitReached ? (
        <div className="mt-4">
          <FormMessage>提交次数已经用完，当前答案仅供查看。</FormMessage>
        </div>
      ) : null}

      <div className="mt-6 space-y-6">
        {initialSurvey.questions.map((question, questionIndex) => (
          <fieldset
            className="rounded-xl border border-[var(--color-border)] p-4 sm:p-5"
            disabled={pending || limitReached}
            key={question.id}
          >
            <legend className="px-2 text-base font-semibold">
              {questionIndex + 1}. {question.prompt}
            </legend>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              {question.allow_multiple ? "多选题" : "单选题"} · 必答
            </p>
            <div className="mt-4 space-y-3">
              {question.options.map((option) => {
                const checked = (answers[question.id] ?? []).includes(option.id);
                return (
                  <label
                    className={
                      "flex cursor-pointer items-center gap-3 rounded-xl border p-4 transition " +
                      (checked
                        ? "border-[var(--color-accent)] bg-[var(--color-action-fill)]"
                        : "border-[var(--color-border)]")
                    }
                    key={option.id}
                  >
                    <input
                      checked={checked}
                      className="size-4 accent-[var(--color-accent)]"
                      name={"intention-question-" + question.id}
                      onChange={() =>
                        toggle(
                          question.id,
                          option.id,
                          question.allow_multiple,
                        )
                      }
                      type={question.allow_multiple ? "checkbox" : "radio"}
                    />
                    <span className="text-sm font-medium">{option.label}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        ))}
      </div>

      <label className="mt-5 block text-sm font-medium">
        补充说明（可选）
        <textarea
          className={inputClassName + " min-h-28 py-3"}
          disabled={pending || limitReached}
          maxLength={4_000}
          onChange={(event) => setFreeText(event.target.value)}
          value={freeText}
        />
      </label>
      <button
        className={buttonClassName + " mt-5 w-full sm:w-auto"}
        disabled={pending || limitReached}
        type="submit"
      >
        {pending
          ? "提交中…"
          : submissionCount > 0
            ? "再次提交问卷"
            : "提交问卷"}
      </button>
    </form>
  );
}
