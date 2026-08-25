"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { FormMessage, inputClassName } from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { AdminRegistrationItem } from "@/lib/api/types";
import {
  registrationStatusLabel,
  statusTagClass,
} from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function AdminCompetitionRegistrationPanel({
  archived,
  competitionId,
  initialRegistrations,
}: Readonly<{
  archived: boolean;
  competitionId: string;
  initialRegistrations: AdminRegistrationItem[];
}>) {
  const router = useRouter();
  const [registrations, setRegistrations] = useState(initialRegistrations);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [pendingUserId, setPendingUserId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function disqualify(item: AdminRegistrationItem) {
    const reason = reasons[item.user_id]?.trim() ?? "";
    if (!reason) {
      setError("取消个人参赛资格必须填写原因。");
      return;
    }
    const teamWarning = item.team_id
      ? "该学生当前在队伍“" + item.team_name + "”中，继续后整队也会被取消资格。"
      : "";
    if (
      !window.confirm(
        "确认取消“" + item.full_name + "”的个人参赛资格？" + teamWarning,
      )
    ) {
      return;
    }
    setPendingUserId(item.user_id);
    setMessage(null);
    setError(null);
    try {
      const updated = await csrfFetch<AdminRegistrationItem>(
        "/admin/competitions/" +
          competitionId +
          "/registrations/" +
          item.user_id +
          "/disqualify",
        {
          method: "POST",
          body: JSON.stringify({ reason }),
        },
      );
      setRegistrations((current) =>
        current.map((registration) =>
          registration.user_id === updated.user_id ? updated : registration,
        ),
      );
      setReasons((current) => ({ ...current, [item.user_id]: "" }));
      setMessage("个人参赛资格已取消，原因仅管理员和该学生本人可见。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPendingUserId(null);
    }
  }

  return (
    <section className="mt-8 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">个人报名资格</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            共 {registrations.length} 条报名记录；取消资格后不能重新报名，原因仅本人和管理员可见。
          </p>
        </div>
        {archived ? (
          <span className="font-mono text-xs text-[var(--color-text-muted)]">
            ARCHIVED · READ ONLY
          </span>
        ) : null}
      </div>

      {message ? <div className="mt-5"><FormMessage tone="success">{message}</FormMessage></div> : null}
      {error ? <div className="mt-5"><FormMessage>{error}</FormMessage></div> : null}

      <div className="mt-5 space-y-4">
        {registrations.map((item) => (
          <article
            className="grid gap-4 border border-[var(--color-border)] p-4 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,24rem)]"
            key={item.user_id}
          >
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="font-medium">{item.full_name}</h3>
                <span
                  className={
                    "border px-2 py-0.5 font-mono text-xs " +
                    statusTagClass(item.status)
                  }
                >
                  {registrationStatusLabel(item.status)}
                </span>
              </div>
              <p className="mt-2 font-mono text-xs text-[var(--color-text-muted)]">
                {item.student_number} · 报名于 {formatDateTime(item.registered_at)}
              </p>
              {item.team_id ? (
                <p className="mt-2 text-sm">
                  当前队伍：
                  <Link
                    className="text-[var(--color-info)]"
                    href={
                      "/admin/competitions/" +
                      competitionId +
                      "/teams/" +
                      item.team_id
                    }
                  >
                    {item.team_name}
                  </Link>
                </p>
              ) : null}
              {item.disqualification_reason ? (
                <p className="mt-3 text-sm text-[var(--color-danger)]">
                  取消资格原因：{item.disqualification_reason}
                </p>
              ) : null}
            </div>

            {item.status !== "disqualified" ? (
              <div className="space-y-3">
                <label className="block text-sm">
                  取消资格原因
                  <textarea
                    aria-label={"取消资格原因（" + item.full_name + "）"}
                    className={inputClassName + " min-h-24 py-3"}
                    disabled={archived || pendingUserId !== null}
                    maxLength={2000}
                    onChange={(event) =>
                      setReasons((current) => ({
                        ...current,
                        [item.user_id]: event.target.value,
                      }))
                    }
                    value={reasons[item.user_id] ?? ""}
                  />
                </label>
                <button
                  className="min-h-11 w-full border border-[var(--color-danger)] px-5 text-[var(--color-danger)]"
                  disabled={archived || pendingUserId !== null}
                  onClick={() => disqualify(item)}
                  type="button"
                >
                  {pendingUserId === item.user_id ? "处理中…" : "取消个人参赛资格"}
                </button>
              </div>
            ) : null}
          </article>
        ))}
        {registrations.length === 0 ? (
          <p className="border border-dashed border-[var(--color-border-strong)] p-6 text-center text-sm text-[var(--color-text-muted)]">
            尚无报名记录。
          </p>
        ) : null}
      </div>
    </section>
  );
}
