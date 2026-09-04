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
  AdminUser,
  AdminUserPage,
  Direction,
  IntentionEmailNotificationResult,
} from "@/lib/api/types";
import { createIdempotencyKey } from "@/lib/idempotency";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

type RecipientScope = "manual" | "direction" | "all";

type NotificationRequest = {
  recipient_scope: RecipientScope;
  recipient_user_ids?: string[];
  direction_ids?: string[];
};

export function IntentionEmailNotifier({
  audience,
  directions,
  surveyId,
  surveyTitle,
}: Readonly<{
  audience: { all_students: boolean; direction_ids: string[] };
  directions: Direction[];
  surveyId: string;
  surveyTitle: string;
}>) {
  const [recipientScope, setRecipientScope] =
    useState<RecipientScope>("manual");
  const [selectedDirectionIds, setSelectedDirectionIds] = useState<string[]>(
    [],
  );
  const [search, setSearch] = useState("");
  const [candidates, setCandidates] = useState<AdminUser[]>([]);
  const [selected, setSelected] = useState<AdminUser[]>([]);
  const [resultTotal, setResultTotal] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeDirections = directions.filter(
    (direction) =>
      direction.is_active &&
      (audience.all_students || audience.direction_ids.includes(direction.id)),
  );

  function selectScope(scope: RecipientScope) {
    setRecipientScope(scope);
    setMessage(null);
    setError(null);
  }

  async function searchMembers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    setError(null);
    const params = new URLSearchParams({
      page: "1",
      page_size: "20",
      status: "active",
      role: "student",
    });
    const normalizedSearch = search.trim();
    if (normalizedSearch) params.set("search", normalizedSearch);
    try {
      const result = await apiFetch<AdminUserPage>(
        "/admin/users?" + params.toString(),
      );
      setCandidates(result.items);
      setResultTotal(result.total);
      setMessage(
        `找到 ${result.total} 名激活学生，当前显示 ${result.items.length} 名。`,
      );
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  function toggleMember(user: AdminUser) {
    const selectedAlready = selected.some((item) => item.id === user.id);
    if (!selectedAlready && selected.length >= 100) {
      setError("一次最多选择 100 名成员。");
      return;
    }
    setError(null);
    setSelected((current) =>
      selectedAlready
        ? current.filter((item) => item.id !== user.id)
        : [...current, user],
    );
  }

  function toggleDirection(directionId: string) {
    const selectedAlready = selectedDirectionIds.includes(directionId);
    if (!selectedAlready && selectedDirectionIds.length >= 100) {
      setError("一次最多选择 100 个技术组。");
      return;
    }
    setError(null);
    setSelectedDirectionIds((current) =>
      selectedAlready
        ? current.filter((item) => item !== directionId)
        : [...current, directionId],
    );
  }

  async function sendNotifications() {
    if (recipientScope === "manual" && selected.length === 0) {
      setError("请先选择至少一名成员。");
      return;
    }
    if (recipientScope === "direction" && selectedDirectionIds.length === 0) {
      setError("请先选择至少一个技术组。");
      return;
    }
    const payload: NotificationRequest = {
      recipient_scope: recipientScope,
    };
    if (recipientScope === "manual") {
      payload.recipient_user_ids = selected.map((item) => item.id);
    } else if (recipientScope === "direction") {
      payload.direction_ids = selectedDirectionIds;
    }

    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const result = await csrfFetch<IntentionEmailNotificationResult>(
        "/admin/intentions/" + surveyId + "/email-notifications",
        {
          method: "POST",
          headers: { "Idempotency-Key": createIdempotencyKey() },
          body: JSON.stringify(payload),
        },
      );
      if (recipientScope === "manual") setSelected([]);
      setMessage(
        result.already_queued_count > 0
          ? `已新增 ${result.queued_count} 封邮件任务；${result.already_queued_count} 名成员本次开放周期已入队，未重复发送。`
          : `已为 ${result.queued_count} 名成员创建邮件任务。`,
      );
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  const sendButtonLabel =
    recipientScope === "manual"
      ? "向已选成员发送邮件"
      : recipientScope === "direction"
        ? "向已选技术组发送邮件"
        : audience.all_students
          ? "向全部激活学生发送邮件"
          : "向问卷全部目标学生发送邮件";
  const sendDisabled =
    pending ||
    (recipientScope === "manual" && selected.length === 0) ||
    (recipientScope === "direction" && selectedDirectionIds.length === 0);

  return (
    <section
      aria-label={"向“" + surveyTitle + "”发送邮件通知"}
      className="mt-5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4"
    >
      <h3 className="text-sm font-semibold">发送邮件通知</h3>
      <p className="mt-2 text-xs text-[var(--color-text-secondary)]">
        可手动选择成员、按技术组或向问卷全部目标学生发送；收件范围由服务端在发送时重新确认，邮件不包含问卷答案或二维码令牌。
      </p>
      {message ? <FormMessage tone="success">{message}</FormMessage> : null}
      {error ? <FormMessage>{error}</FormMessage> : null}

      <fieldset className="mt-4">
        <legend className="text-sm font-medium">发送范围</legend>
        <div className="mt-2 flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input
              checked={recipientScope === "manual"}
              name={"intention-email-scope-" + surveyId}
              onChange={() => selectScope("manual")}
              type="radio"
            />
            手动选择成员
          </label>
          <label className="flex items-center gap-2">
            <input
              checked={recipientScope === "direction"}
              name={"intention-email-scope-" + surveyId}
              onChange={() => selectScope("direction")}
              type="radio"
            />
            按技术组
          </label>
          <label className="flex items-center gap-2">
            <input
              checked={recipientScope === "all"}
              name={"intention-email-scope-" + surveyId}
              onChange={() => selectScope("all")}
              type="radio"
            />
            {audience.all_students ? "全部激活学生" : "问卷全部目标学生"}
          </label>
        </div>
      </fieldset>

      {recipientScope === "direction" ? (
        <fieldset className="mt-4">
          <legend className="text-sm font-medium">
            选择技术组（已选择 {selectedDirectionIds.length} / 100 个）
          </legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {activeDirections.map((direction) => (
              <label
                className="flex cursor-pointer items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm"
                key={direction.id}
              >
                <input
                  checked={selectedDirectionIds.includes(direction.id)}
                  className="size-4 accent-[var(--color-accent)]"
                  disabled={pending}
                  onChange={() => toggleDirection(direction.id)}
                  type="checkbox"
                />
                <span>{direction.name}</span>
              </label>
            ))}
          </div>
          {activeDirections.length === 0 ? (
            <p className="mt-2 text-xs text-[var(--color-text-muted)]">
              当前没有可用的激活技术组。
            </p>
          ) : null}
        </fieldset>
      ) : null}

      {recipientScope === "all" ? (
        <p className="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm">
          将向发送时
          {audience.all_students ? "全部激活学生" : "该问卷技术组内的全部激活学生"}
          创建邮件任务；同一开放周期已入队的成员不会重复发送。
        </p>
      ) : null}

      {recipientScope === "manual" ? (
        <>
      <form
        className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end"
        onSubmit={searchMembers}
      >
        <label className="min-w-0 flex-1 text-sm font-medium">
          搜索成员
          <input
            className={inputClassName}
            maxLength={200}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="姓名、学号或学校邮箱"
            value={search}
          />
        </label>
        <button
          className={commandButtonClassName}
          disabled={pending}
          type="submit"
        >
          搜索成员
        </button>
      </form>

      {resultTotal !== null ? (
        <div className="mt-4 space-y-2">
          {candidates.map((user) => (
            <label
              className="flex cursor-pointer items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm"
              key={user.id}
            >
              <input
                checked={selected.some((item) => item.id === user.id)}
                className="mt-1 size-4 accent-[var(--color-accent)]"
                onChange={() => toggleMember(user)}
                type="checkbox"
              />
              <span className="min-w-0">
                <span className="block font-medium">{user.full_name}</span>
                <span className="mt-1 block break-all text-xs text-[var(--color-text-muted)]">
                  {user.student_number} · {user.email}
                </span>
              </span>
            </label>
          ))}
          {candidates.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              没有匹配的激活学生。
            </p>
          ) : null}
          {resultTotal > candidates.length ? (
            <p className="text-xs text-[var(--color-text-muted)]">
              当前显示前 {candidates.length} 名；请继续用姓名、学号或邮箱缩小范围。
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 rounded-lg border border-dashed border-[var(--color-border-strong)] p-3">
        <p className="text-sm font-medium">已选择 {selected.length} / 100 名</p>
        {selected.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {selected.map((user) => (
              <button
                aria-label={"移除成员“" + user.full_name + "”"}
                className={commandButtonClassName}
                key={user.id}
                onClick={() => toggleMember(user)}
                type="button"
              >
                {user.full_name} ×
              </button>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-xs text-[var(--color-text-muted)]">
            搜索并勾选需要接收提醒的成员。
          </p>
        )}
      </div>
        </>
      ) : null}

      <button
        className={buttonClassName + " mt-4"}
        disabled={sendDisabled}
        onClick={sendNotifications}
        type="button"
      >
        {pending ? "处理中…" : sendButtonLabel}
      </button>
    </section>
  );
}
