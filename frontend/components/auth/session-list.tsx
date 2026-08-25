"use client";

import { useState } from "react";

import { buttonClassName, FormMessage } from "@/components/ui/form-controls";
import { csrfFetch } from "@/lib/api/client";
import type { Session } from "@/lib/api/types";

function displayTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN");
}

export function SessionList({
  initialSessions,
}: Readonly<{ initialSessions: Session[] }>) {
  const [sessions, setSessions] = useState(initialSessions);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function revoke(sessionId: string) {
    setPendingId(sessionId);
    setMessage(null);
    try {
      await csrfFetch<void>("/auth/sessions/" + sessionId, {
        method: "DELETE",
      });
      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId
            ? { ...session, revoked_at: new Date().toISOString() }
            : session,
        ),
      );
      setMessage("该登录设备已撤销。");
    } catch {
      setMessage("撤销失败，请刷新页面后重试。");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="mt-8 space-y-4">
      {message ? <FormMessage tone="info">{message}</FormMessage> : null}
      {sessions.map((session) => (
        <article
          className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
          key={session.id}
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="font-medium">{session.user_agent_summary}</h2>
                {session.is_current ? (
                  <span className="bg-[var(--color-success)] px-2 py-0.5 text-xs text-black">
                    当前设备
                  </span>
                ) : null}
                {session.revoked_at ? (
                  <span className="text-xs text-[var(--color-text-muted)]">
                    已撤销
                  </span>
                ) : null}
              </div>
              <p className="mt-2 font-mono text-xs text-[var(--color-text-secondary)]">
                {session.ip_prefix}
              </p>
            </div>
            {!session.is_current && session.revoked_at === null ? (
              <button
                className={buttonClassName}
                disabled={pendingId === session.id}
                onClick={() => revoke(session.id)}
                type="button"
              >
                {pendingId === session.id ? "撤销中…" : "撤销会话"}
              </button>
            ) : null}
          </div>
          <dl className="mt-5 grid gap-3 text-sm text-[var(--color-text-secondary)] sm:grid-cols-3">
            <div>
              <dt className="text-[var(--color-text-muted)]">创建时间</dt>
              <dd>{displayTime(session.created_at)}</dd>
            </div>
            <div>
              <dt className="text-[var(--color-text-muted)]">最近活动</dt>
              <dd>{displayTime(session.last_seen_at)}</dd>
            </div>
            <div>
              <dt className="text-[var(--color-text-muted)]">绝对到期</dt>
              <dd>{displayTime(session.absolute_expires_at)}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}
