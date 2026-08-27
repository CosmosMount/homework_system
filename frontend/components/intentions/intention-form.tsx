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

export function IntentionForm({
  initialSurvey,
}: Readonly<{ initialSurvey: IntentionSurvey }>) {
  const router = useRouter();
  const [selected, setSelected] = useState<string[]>(
    initialSurvey.response?.selected_option_ids ?? [],
  );
  const [freeText, setFreeText] = useState(
    initialSurvey.response?.free_text ?? "",
  );
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggle(optionId: string) {
    setSelected((current) => {
      if (!initialSurvey.allow_multiple) {
        return [optionId];
      }
      return current.includes(optionId)
        ? current.filter((item) => item !== optionId)
        : [...current, optionId];
    });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selected.length === 0) {
      setError("请选择至少一个选项。");
      return;
    }

    setPending(true);
    setError(null);
    setMessage(null);
    try {
      await csrfFetch(
        "/intentions/" + initialSurvey.id + "/response",
        {
          method: "PUT",
          body: JSON.stringify({
            selected_option_ids: selected,
            free_text: freeText.trim() || null,
          }),
        },
      );
      setMessage("意向已保存，可以在调查关闭前继续修改。");
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
        <h2 className="text-xl font-semibold">你的选择</h2>
        <span className="text-sm text-[var(--color-text-muted)]">
          {initialSurvey.allow_multiple ? "可多选" : "单选"}
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

      <div className="mt-5 space-y-3">
        {initialSurvey.options.map((option) => {
          const checked = selected.includes(option.id);
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
                name="intention-option"
                onChange={() => toggle(option.id)}
                type={initialSurvey.allow_multiple ? "checkbox" : "radio"}
              />
              <span className="text-sm font-medium">{option.label}</span>
            </label>
          );
        })}
      </div>

      <label className="mt-5 block text-sm font-medium">
        补充说明（可选）
        <textarea
          className={inputClassName + " min-h-28 py-3"}
          maxLength={4_000}
          onChange={(event) => setFreeText(event.target.value)}
          value={freeText}
        />
      </label>
      <button
        className={buttonClassName + " mt-5 w-full sm:w-auto"}
        disabled={pending}
        type="submit"
      >
        {pending
          ? "保存中…"
          : initialSurvey.response
            ? "更新我的意向"
            : "提交我的意向"}
      </button>
    </form>
  );
}
