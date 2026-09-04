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
  AdminIntentionSurveyDetail,
  Direction,
  IntentionDirectionAssignmentResult,
  IntentionQuestion,
} from "@/lib/api/types";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

function firstQuestion(
  detail: AdminIntentionSurveyDetail,
): IntentionQuestion | null {
  return (
    [...detail.questions].sort(
      (left, right) =>
        left.display_order - right.display_order || left.id.localeCompare(right.id),
    )[0] ?? null
  );
}

export function IntentionDirectionAssigner({
  directions,
  disabled,
  surveyId,
  surveyTitle,
}: Readonly<{
  directions: Direction[];
  disabled: boolean;
  surveyId: string;
  surveyTitle: string;
}>) {
  const [detail, setDetail] = useState<AdminIntentionSurveyDetail | null>(null);
  const [mappings, setMappings] = useState<Record<string, string>>({});
  const [result, setResult] =
    useState<IntentionDirectionAssignmentResult | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeDirections = directions.filter(
    (direction) => direction.is_active,
  );
  const question = detail ? firstQuestion(detail) : null;
  const options = question
    ? [...question.options].sort(
        (left, right) =>
          left.display_order - right.display_order ||
          left.id.localeCompare(right.id),
      )
    : [];
  const mappingComplete =
    options.length > 0 &&
    options.every((option) => Boolean(mappings[option.id]));
  const busy = disabled || pending;

  async function loadQuestion() {
    setPending(true);
    setMessage(null);
    setError(null);
    setResult(null);
    try {
      const current = await apiFetch<AdminIntentionSurveyDetail>(
        "/admin/intentions/" + surveyId,
      );
      const currentFirstQuestion = firstQuestion(current);
      setDetail(current);
      setMappings(
        Object.fromEntries(
          (currentFirstQuestion?.options ?? []).map((option) => [option.id, ""]),
        ),
      );
      if (!currentFirstQuestion) {
        setError("问卷没有可用于配置技术方向的第一题。");
      } else if (currentFirstQuestion.allow_multiple) {
        setError("问卷第一题是多选题，无法据此配置唯一技术方向。");
      } else if (activeDirections.length === 0) {
        setError("当前没有启用中的技术方向，请先在分类管理中启用方向。");
      } else {
        setMessage("第一志愿选项已加载，请为每个选项选择技术方向。");
      }
    } catch (nextError) {
      setDetail(null);
      setMappings({});
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function applyDirections(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question || question.allow_multiple || !mappingComplete) {
      setError("请先为第一志愿的每个选项选择一个技术方向。");
      return;
    }
    const confirmed = window.confirm(
      "确认按所有人的最新第一志愿覆盖激活学生已有技术方向吗？此操作不会修改问卷答案，也不会重算已发布作业的固定受众；开放问卷后续改答不会自动同步。",
    );
    if (!confirmed) return;

    setPending(true);
    setMessage(null);
    setError(null);
    setResult(null);
    try {
      const applied = await csrfFetch<IntentionDirectionAssignmentResult>(
        "/admin/intentions/" +
          surveyId +
          "/apply-first-choice-directions",
        {
          method: "POST",
          body: JSON.stringify({
            question_id: question.id,
            option_mappings: options.map((option) => ({
              option_id: option.id,
              direction_id: mappings[option.id],
            })),
            confirm_overwrite: true,
          }),
        },
      );
      setResult(applied);
      setMessage("已按当前最新第一志愿完成技术方向配置。");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  return (
    <section
      aria-label={"为“" + surveyTitle + "”按第一志愿配置技术方向"}
      className="mt-5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4"
    >
      <h3 className="text-sm font-semibold">按第一志愿配置技术方向</h3>
      <p className="mt-2 text-xs text-[var(--color-text-secondary)]">
        读取问卷第一道单选题，将每个选项显式映射到启用中的技术方向。执行时只覆盖已提交问卷的激活学生。
      </p>

      <button
        className={commandButtonClassName + " mt-4"}
        disabled={busy}
        onClick={loadQuestion}
        type="button"
      >
        {pending ? "处理中…" : detail ? "刷新第一志愿选项" : "配置第一志愿方向"}
      </button>

      {message ? (
        <div className="mt-3">
          <FormMessage tone="success">{message}</FormMessage>
        </div>
      ) : null}
      {error ? (
        <div className="mt-3">
          <FormMessage>{error}</FormMessage>
        </div>
      ) : null}

      {question &&
      !question.allow_multiple &&
      activeDirections.length > 0 ? (
        <form
          className="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
          onSubmit={applyDirections}
        >
          <p className="text-sm font-medium">第一题：{question.prompt}</p>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {options.map((option) => {
              const inputId =
                "intention-direction-" + surveyId + "-" + option.id;
              return (
                <label
                  className="block text-sm font-medium"
                  htmlFor={inputId}
                  key={option.id}
                >
                  {option.label} 对应技术方向
                  <select
                    aria-label={option.label + "对应技术方向"}
                    className={inputClassName}
                    disabled={busy}
                    id={inputId}
                    onChange={(event) =>
                      setMappings((current) => ({
                        ...current,
                        [option.id]: event.target.value,
                      }))
                    }
                    value={mappings[option.id] ?? ""}
                  >
                    <option value="">请选择技术方向</option>
                    {activeDirections.map((direction) => (
                      <option key={direction.id} value={direction.id}>
                        {direction.name}
                      </option>
                    ))}
                  </select>
                </label>
              );
            })}
          </div>
          <p className="mt-4 text-xs text-[var(--color-text-secondary)]">
            将覆盖符合条件学生的已有方向；不会改动问卷答案，也不会重算已发布作业的固定受众。若问卷仍开放，后续改答需再次手动执行。
          </p>
          <button
            className={buttonClassName + " mt-4"}
            disabled={busy || !mappingComplete}
            type="submit"
          >
            {pending ? "处理中…" : "确认按第一志愿配置方向"}
          </button>
        </form>
      ) : null}

      {result ? (
        <dl
          aria-label="方向配置结果"
          className="mt-4 grid grid-cols-2 gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm sm:grid-cols-4"
        >
          <div>
            <dt className="text-[var(--color-text-muted)]">符合条件</dt>
            <dd className="mt-1 font-semibold">{result.eligible_response_count} 人</dd>
          </div>
          <div>
            <dt className="text-[var(--color-text-muted)]">实际更新</dt>
            <dd className="mt-1 font-semibold">{result.updated_count} 人</dd>
          </div>
          <div>
            <dt className="text-[var(--color-text-muted)]">方向未变化</dt>
            <dd className="mt-1 font-semibold">{result.unchanged_count} 人</dd>
          </div>
          <div>
            <dt className="text-[var(--color-text-muted)]">跳过回答</dt>
            <dd className="mt-1 font-semibold">{result.skipped_response_count} 人</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}
