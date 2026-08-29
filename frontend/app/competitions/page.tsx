import { redirect } from "next/navigation";

import { CompetitionRegistrationActions } from "@/components/competitions/registration-actions";
import { TeamDirectoryPanel } from "@/components/competitions/team-directory-panel";
import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import { getCompetition, getCompetitionTeams, getCompetitions, getDashboard, requireUser } from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";
import { competitionStatusLabel, statusTagClass } from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

type CompetitionsPageProps = Readonly<{
  searchParams: Promise<{ q?: string; page?: string }>;
}>;

export default async function CompetitionsPage({ searchParams }: CompetitionsPageProps) {
  const [user, dashboard, filters] = await Promise.all([
    requireUser(),
    getDashboard(),
    searchParams,
  ]);
  if (isAdminView(user)) {
    redirect("/admin/competitions");
  }

  const query = (filters.q ?? "").trim().slice(0, 120);
  const requestedPage = Number(filters.page ?? "1");
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const summaries = await getCompetitions("page=1&page_size=100");
  const currentSummary = summaries.items.find((item) => item.status !== "archived") ?? null;
  const [competition, teams] = currentSummary
    ? await Promise.all([
        getCompetition(currentSummary.id),
        getCompetitionTeams(
          currentSummary.id,
          new URLSearchParams({
            ...(query ? { query } : {}),
            page: String(page),
            page_size: "20",
          }).toString(),
        ),
      ])
    : [null, null];

  return (
    <AppShell unreadCounts={dashboard.unread_counts} user={user}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / CAMPUS COMPETITION
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">校内赛队伍中心</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        这里仅展示当前校内赛。报名后可创建队伍、使用邀请码加入，或申请自动分配。
      </p>

      {competition ? (
        <>
          <article className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={"border px-2 py-0.5 text-xs " + statusTagClass(competition.status)}>
                    {competitionStatusLabel(competition.status)}
                  </span>
                  <span className="rounded-full bg-[var(--color-surface-hover)] px-2.5 py-1 text-xs text-[var(--color-text-muted)]">
                    当前校内赛
                  </span>
                </div>
                <h2 className="mt-3 text-2xl font-semibold">{competition.name}</h2>
                <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                  报名截止 {formatDateTime(competition.registration_end)}
                  <span className="mx-2 text-[var(--color-border-strong)]">·</span>
                  队伍人数 {competition.min_team_size}–{competition.max_team_size}
                </p>
              </div>
              <p className="text-right font-mono text-xs text-[var(--color-text-muted)]">
                赛事结束<br />{formatDateTime(competition.submission_end)}
              </p>
            </div>
            <div className="mt-6 border-t border-[var(--color-border)] pt-5">
              <SafeHtml sanitizedHtml={competition.description_html} />
            </div>
          </article>
          <CompetitionRegistrationActions competition={competition} />
          {teams ? (
            <TeamDirectoryPanel initialTeams={teams} query={query} />
          ) : null}
        </>
      ) : (
        <section className="mt-8 rounded-2xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)] p-10 text-center">
          <h2 className="text-xl font-semibold">尚未配置校内赛</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            管理员配置并发布校内赛后，这里会显示公告和队伍目录。
          </p>
        </section>
      )}
    </AppShell>
  );
}
