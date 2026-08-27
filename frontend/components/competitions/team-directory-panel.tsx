import Link from "next/link";

import { buttonClassName, inputClassName } from "@/components/ui/form-controls";
import type { TeamDirectoryPage } from "@/lib/api/types";
import { statusTagClass, teamStatusLabel } from "@/lib/competition-labels";

export function TeamDirectoryPanel({
  initialTeams,
  query,
}: Readonly<{
  initialTeams: TeamDirectoryPage;
  query: string;
}>) {
  const page = initialTeams.page;
  const hasNext = page * initialTeams.page_size < initialTeams.total;

  function pageHref(nextPage: number): string {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (nextPage > 1) params.set("page", String(nextPage));
    const suffix = params.toString();
    return "/competitions" + (suffix ? "?" + suffix : "");
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
                  {team.member_count} / {team.max_team_size} 人
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
              {team.can_join
                ? "报名期内可通过邀请码加入"
                : "当前不可加入，可查看队伍状态或等待管理员安排"}
            </p>
          </article>
        ))}
      </div>

      {initialTeams.items.length === 0 ? (
        <p className="mt-5 rounded-xl border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
          暂无匹配队伍。报名后可以创建队伍、输入邀请码或申请自动分配。
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
