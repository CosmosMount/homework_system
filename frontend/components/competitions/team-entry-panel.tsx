"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { AutoAssign, Team, TeamCreated } from "@/lib/api/types";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function TeamEntryPanel({ hasTeam }: Readonly<{ hasTeam: boolean }>) {
  const router = useRouter();
  const [teamName, setTeamName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [enteredTeam, setEnteredTeam] = useState(false);
  const joined = hasTeam || enteredTeam;
  const [oneTimeInviteCode, setOneTimeInviteCode] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function begin() {
    setPending(true);
    setMessage(null);
    setError(null);
  }

  function complete(nextMessage: string, code: string | null = null) {
    setEnteredTeam(true);
    setOneTimeInviteCode(code);
    setMessage(nextMessage);
    router.refresh();
  }

  async function createTeam() {
    const normalizedName = teamName.trim();
    if (!normalizedName) {
      setError("请输入队伍名称。");
      return;
    }
    begin();
    try {
      const result = await csrfFetch<TeamCreated>("/teams", {
        method: "POST",
        body: JSON.stringify({ name: normalizedName }),
      });
      setTeamName("");
      complete("队伍已创建。邀请码只显示这一次，请立即保存。", result.invite_code);
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function joinTeam() {
    const normalizedCode = inviteCode.trim();
    if (!normalizedCode) {
      setError("请输入邀请码。");
      return;
    }
    begin();
    try {
      await csrfFetch<Team>("/teams/join", {
        method: "POST",
        body: JSON.stringify({ invite_code: normalizedCode }),
      });
      setInviteCode("");
      complete("已加入队伍。", null);
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function autoAssign() {
    if (!window.confirm("系统会优先加入未满队伍；没有可加入队伍时将自动创建一支队伍。确认继续？")) {
      return;
    }
    begin();
    try {
      const result = await csrfFetch<AutoAssign>("/teams/auto-assign", {
        method: "POST",
      });
      complete(
        result.assignment === "joined" ? "已自动加入队伍。" : "已自动创建队伍。邀请码只显示这一次，请立即保存。",
        result.invite_code,
      );
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
      <div>
        <p className="text-xs font-medium tracking-[0.14em] text-[var(--color-text-muted)]">
          TEAM ENTRY
        </p>
        <h2 className="mt-1 text-xl font-semibold">
          {joined ? "我的组队状态" : "开始组队"}
        </h2>
      </div>

      {message ? <div className="mt-5"><FormMessage tone="success">{message}</FormMessage></div> : null}
      {error ? <div className="mt-5"><FormMessage>{error}</FormMessage></div> : null}
      {oneTimeInviteCode ? (
        <div className="mt-5 border border-[var(--color-warning)] bg-[var(--color-bg)] p-4">
          <p className="text-sm text-[var(--color-warning)]">邀请码（仅显示一次）</p>
          <code className="mt-2 block select-all text-xl tracking-[0.14em]">
            {oneTimeInviteCode}
          </code>
        </div>
      ) : null}

      {!joined ? (
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <div className="space-y-3 border border-[var(--color-border)] p-4">
            <label className="block text-sm font-medium">
              队伍名称
              <input
                className={inputClassName}
                disabled={pending}
                maxLength={120}
                onChange={(event) => setTeamName(event.target.value)}
                placeholder="输入新队伍名称"
                value={teamName}
              />
            </label>
            <button className={buttonClassName + " w-full"} disabled={pending} onClick={createTeam} type="button">
              创建队伍
            </button>
          </div>
          <div className="space-y-3 border border-[var(--color-border)] p-4">
            <label className="block text-sm font-medium">
              邀请码
              <input
                className={inputClassName}
                disabled={pending}
                maxLength={64}
                onChange={(event) => setInviteCode(event.target.value)}
                placeholder="输入队长提供的邀请码"
                value={inviteCode}
              />
            </label>
            <button className={buttonClassName + " w-full"} disabled={pending} onClick={joinTeam} type="button">
              加入队伍
            </button>
          </div>
          <div className="lg:col-span-2">
            <button
              className="min-h-11 w-full border border-[var(--color-info)] px-5 text-[var(--color-info)] disabled:cursor-not-allowed disabled:opacity-60"
              disabled={pending}
              onClick={autoAssign}
              type="button"
            >
              {pending ? "处理中…" : "自动分配队伍"}
            </button>
          </div>
        </div>
      ) : (
        <p className="mt-5 text-sm text-[var(--color-text-secondary)]">
          你已经加入队伍，可在下方查看成员并进行允许的队伍操作。
        </p>
      )}
    </section>
  );
}
