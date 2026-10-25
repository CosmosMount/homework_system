"use client";

import Link from "next/link";
import { useState } from "react";

import { buttonClassName, FormMessage, inputClassName } from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { TeamApplication, TeamDirectoryPage } from "@/lib/api/types";
import { statusTagClass, teamStatusLabel } from "@/lib/competition-labels";

export function TeamDirectoryPanel({
  initialTeams,
  query,
  currentTeamId,
  initialApplications,
}: Readonly<{
  initialTeams: TeamDirectoryPage;
  query: string;
  currentTeamId: string | null;
  initialApplications: TeamApplication[];
}>) {
  const [pendingTeamIds, setPendingTeamIds] = useState<string[]>(initialApplications.map((item) => item.team_id));
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const page = initialTeams.page;
  const hasNext = page * initialTeams.page_size < initialTeams.total;

  function pageHref(nextPage: number): string {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (nextPage > 1) params.set("page", String(nextPage));
    const suffix = params.toString();
    return "/competitions" + (suffix ? "?" + suffix : "");
  }

  async function apply(teamId: string) {
    setSubmittingId(teamId);
    setMessage(null);
    setError(null);
    try {
      await csrfFetch<TeamApplication>(`/teams/${teamId}/applications`, { method: "POST" });
      setPendingTeamIds((current) => [...new Set([...current, teamId])]);
      setMessage("申请已提交，队长将收到邮件提醒。获批后会自动加入或更换队伍。");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "提交申请失败，请稍后重试。");
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <section className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium tracking-[0.14em] text-[var(--color-text-muted)]">
            TEAM DIRECTORY
          </p>
          <h2 className="mt-1 text-xl font-semibold">队伍目录</h2>
        </div>
        <p className="text-sm text-[var(--color-text-secondary)]">
          共 {initialTeams.total} 支队伍
        </p>
      </div>

      <form className="mt-5 flex flex-col gap-3 sm:flex-row" role="search">
        <label className="min-w-0 flex-1 text-sm font-medium">
          搜索队伍名称
          <input
            className={inputClassName}
            defaultValue={query}
            maxLength={120}
            name="q"
            placeholder="例如：原子队"
            type="search"
          />
        </label>
        <button
          className={buttonClassName + " sm:self-end"}
          type="submit"
        >
          搜索
        </button>
      </form>

      {message ? <div className="mt-4"><FormMessage tone="success">{message}</FormMessage></div> : null}
      {error ? <div className="mt-4"><FormMessage>{error}</FormMessage></div> : null}

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {initialTeams.items.map((team) => (
          <article
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4"
            key={team.id}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-medium">{team.name}</h3>
                <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
                  {team.member_count} / {team.max_members} 人
                </p>
              </div>
              <span
                className={
                  "border px-2 py-0.5 text-xs " + statusTagClass(team.status)
                }
              >
                {teamStatusLabel(team.status)}
              </span>
            </div>
            <p className="mt-3 text-xs text-[var(--color-text-muted)]">
              {team.id === currentTeamId ? "当前队伍" : team.can_apply ? "可向队长申请加入" : "当前不可申请（容量、技术方向或队长身份限制）"}
            </p>
            {team.can_apply ? (
              <button
                className="mt-3 min-h-10 border border-[var(--color-info)] px-4 text-sm text-[var(--color-info)] disabled:opacity-60"
                disabled={pendingTeamIds.includes(team.id) || submittingId !== null}
                onClick={() => apply(team.id)}
                type="button"
              >
                {pendingTeamIds.includes(team.id) ? "已申请" : submittingId === team.id ? "提交中…" : currentTeamId ? "申请更换到此队" : "申请加入"}
              </button>
            ) : null}
          </article>
        ))}
      </div>

      {initialTeams.items.length === 0 ? (
        <p className="mt-5 rounded-xl border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
          暂无匹配队伍。你可以直接创建队伍、输入邀请码或申请自动分配。
        </p>
      ) : null}

      <nav
        aria-label="队伍目录分页"
        className="mt-5 flex items-center justify-between text-sm"
      >
        {page > 1 ? (
          <Link
            className="text-[var(--color-info)]"
            href={pageHref(page - 1)}
          >
            ← 上一页
          </Link>
        ) : (
          <span />
        )}
        <span className="font-mono text-xs text-[var(--color-text-muted)]">
          第 {page} 页
        </span>
        {hasNext ? (
          <Link
            className="text-[var(--color-info)]"
            href={pageHref(page + 1)}
          >
            下一页 →
          </Link>
        ) : (
          <span />
        )}
      </nav>
      <p className="mt-4 text-xs text-[var(--color-text-muted)]">
        为保护隐私，目录不显示邀请码和成员姓名。
      </p>
    </section>
  );
}
