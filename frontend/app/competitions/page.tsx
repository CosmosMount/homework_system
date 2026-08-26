import Link from "next/link";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { buttonClassName, inputClassName } from "@/components/ui/form-controls";
import {
  getCompetitions,
  getDashboard,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";
import {
  competitionStatusLabel,
  registrationStatusLabel,
  statusTagClass,
  teamStatusLabel,
} from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

type CompetitionsPageProps = Readonly<{
  searchParams: Promise<{ q?: string; status?: string; page?: string }>;
}>;

function pageHref(page: number, query: string, status: string): string {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (status !== "all") params.set("status", status);
  if (page > 1) params.set("page", String(page));
  const suffix = params.toString();
  return suffix ? "/competitions?" + suffix : "/competitions";
}

export default async function CompetitionsPage({
  searchParams,
}: CompetitionsPageProps) {
  const [user, dashboard, filters] = await Promise.all([
    requireUser(),
    getDashboard(),
    searchParams,
  ]);
  if (isAdminView(user)) {
    redirect("/admin/competitions");
  }

  const query = (filters.q ?? "").trim().slice(0, 200);
  const allowedStatuses = new Set([
    "all",
    "registration_open",
    "registration_closed",
    "submission_open",
    "submission_closed",
    "archived",
  ]);
  const status = allowedStatuses.has(filters.status ?? "")
    ? (filters.status ?? "all")
    : "all";
  const requestedPage = Number(filters.page ?? "1");
  const page =
    Number.isSafeInteger(requestedPage) && requestedPage > 0
      ? requestedPage
      : 1;
  const apiParams = new URLSearchParams({
    page: String(page),
    page_size: "20",
  });
  if (status !== "all") apiParams.set("status", status);
  if (query) apiParams.set("query", query);
  const competitions = await getCompetitions(apiParams.toString());
  const hasNext = page * competitions.page_size < competitions.total;

  return (
    <AppShell unreadCount={dashboard.unread_count} user={user}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / COMPETITIONS
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">校内赛</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        阅读校内赛公告，报名后创建或加入队伍；报名结束自动锁定队伍。
      </p>

      <form className="mt-8 grid gap-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 md:grid-cols-[minmax(0,1fr)_14rem_auto] md:items-end">
        <label className="text-sm font-medium">
          搜索赛事
          <input
            className={inputClassName}
            defaultValue={query}
            maxLength={200}
            name="q"
            placeholder="输入赛事名称"
            type="search"
          />
        </label>
        <label className="text-sm font-medium">
          阶段
          <select className={inputClassName} defaultValue={status} name="status">
            <option value="all">全部</option>
            <option value="registration_open">报名中</option>
            <option value="registration_closed">报名已结束</option>
            <option value="submission_open">赛事进行中</option>
            <option value="submission_closed">赛事已结束</option>
            <option value="archived">已归档</option>
          </select>
        </label>
        <button
          className={buttonClassName}
          type="submit"
        >
          筛选
        </button>
      </form>

      <p className="mt-6 text-sm text-[var(--color-text-muted)]">
        共 {competitions.total} 场
      </p>
      {competitions.items.length ? (
        <div className="mt-4 space-y-3">
          {competitions.items.map((competition) => {
            const keyTime =
              competition.status === "registration_open"
                ? competition.registration_end
                : competition.submission_end;
            return (
              <Link
                className="block border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition hover:border-[var(--color-border-strong)]"
                href={"/competitions/" + competition.id}
                key={competition.id}
              >
                <div className="flex flex-wrap items-start justify-between gap-5">
                  <div>
                    <div className="flex flex-wrap gap-2 font-mono text-xs">
                      <span
                        className={
                          "border px-2 py-0.5 " +
                          statusTagClass(competition.status)
                        }
                      >
                        {competitionStatusLabel(competition.status)}
                      </span>
                      <span className="border border-[var(--color-border-strong)] px-2 py-0.5">
                        {registrationStatusLabel(
                          competition.registration_status,
                        )}
                      </span>
                      {competition.team_status ? (
                        <span className="border border-[var(--color-info)] px-2 py-0.5 text-[var(--color-info)]">
                          {competition.team_name} ·{" "}
                          {teamStatusLabel(competition.team_status)}
                        </span>
                      ) : null}
                    </div>
                    <h2 className="mt-3 text-xl font-medium">
                      {competition.name}
                    </h2>
                    <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                      队伍人数 {competition.min_team_size}–
                      {competition.max_team_size}
                    </p>
                  </div>
                  <time
                    className="font-mono text-xs text-[var(--color-text-muted)]"
                    dateTime={keyTime}
                  >
                    {competition.status === "registration_open"
                      ? "报名截止 "
                      : "赛事结束 "}
                    {formatDateTime(keyTime)}
                  </time>
                </div>
              </Link>
            );
          })}
        </div>
      ) : (
        <p className="mt-4 border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
          没有符合当前筛选条件的赛事。
        </p>
      )}

      <nav
        aria-label="赛事分页"
        className="mt-8 flex items-center justify-between"
      >
        {page > 1 ? (
          <Link
            className="min-h-11 border border-[var(--color-border-strong)] px-5 py-2"
            href={pageHref(page - 1, query, status)}
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
            className="min-h-11 border border-[var(--color-border-strong)] px-5 py-2"
            href={pageHref(page + 1, query, status)}
          >
            下一页 →
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </AppShell>
  );
}
