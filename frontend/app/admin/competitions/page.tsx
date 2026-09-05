import Link from "next/link";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AppShell } from "@/components/layout/app-shell";
import { buttonClassName, inputClassName } from "@/components/ui/form-controls";
import { getAdminTeams, requireAdmin } from "@/lib/api/server";
import { statusTagClass, teamStatusLabel } from "@/lib/competition-labels";

type AdminCompetitionsPageProps = Readonly<{
  searchParams: Promise<{ q?: string; page?: string }>;
}>;

export default async function AdminCompetitionsPage({
  searchParams,
}: AdminCompetitionsPageProps) {
  const [admin, filters] = await Promise.all([requireAdmin(), searchParams]);
  const query = (filters.q ?? "").trim().slice(0, 120);
  const requestedPage = Number(filters.page ?? "1");
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const teams = await getAdminTeams(
    new URLSearchParams({
      ...(query ? { query } : {}),
      page: String(page),
      page_size: "20",
    }).toString(),
  );
  const hasNext = page * teams.page_size < teams.total;

  function pageHref(nextPage: number): string {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (nextPage > 1) params.set("page", String(nextPage));
    const suffix = params.toString();
    return "/admin/competitions" + (suffix ? "?" + suffix : "");
  }

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / CAMPUS TEAMS"
        title="校内赛队伍"
        description="此页面只管理独立队伍；学生无需等待管理员创建赛事即可直接组队。"
      />

      <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-medium tracking-[0.14em] text-[var(--color-text-muted)]">
              TEAMS
            </p>
            <h2 className="mt-1 text-xl font-semibold">队伍目录</h2>
          </div>
          <p className="text-sm text-[var(--color-text-secondary)]">
            共 {teams.total} 支队伍
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
              placeholder="输入队伍名称"
              type="search"
            />
          </label>
          <button className={buttonClassName + " sm:self-end"} type="submit">
            搜索
          </button>
        </form>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {teams.items.map((team) => (
            <Link
              className="group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 transition hover:-translate-y-0.5 hover:border-[var(--color-accent)] hover:shadow-[var(--shadow-card)]"
              href={"/admin/competitions/" + team.id}
              key={team.id}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium group-hover:text-[var(--color-accent-hover)]">
                    {team.name}
                  </p>
                  <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
                    {team.member_count} / {team.max_members} 人
                  </p>
                </div>
                <span className={"border px-2 py-0.5 text-xs " + statusTagClass(team.status)}>
                  {teamStatusLabel(team.status)}
                </span>
              </div>
            </Link>
          ))}
        </div>

        {teams.items.length === 0 ? (
          <p className="mt-5 rounded-xl border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
            暂无匹配队伍。
          </p>
        ) : null}

        <nav aria-label="管理员队伍目录分页" className="mt-5 flex items-center justify-between text-sm">
          {page > 1 ? (
            <Link className="text-[var(--color-info)]" href={pageHref(page - 1)}>
              ← 上一页
            </Link>
          ) : (
            <span />
          )}
          <span className="font-mono text-xs text-[var(--color-text-muted)]">第 {page} 页</span>
          {hasNext ? (
            <Link className="text-[var(--color-info)]" href={pageHref(page + 1)}>
              下一页 →
            </Link>
          ) : (
            <span />
          )}
        </nav>
      </section>
    </AppShell>
  );
}
