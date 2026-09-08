import Link from "next/link";
import { redirect } from "next/navigation";

import { TeamEntryPanel } from "@/components/competitions/team-entry-panel";
import { TeamDirectoryPanel } from "@/components/competitions/team-directory-panel";
import { TeamManagementPanel } from "@/components/competitions/team-management-panel";
import { AppShell } from "@/components/layout/app-shell";
import {
  getDashboard,
  getMyTeam,
  getTeams,
  getTeamSettings,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";

type CompetitionsPageProps = Readonly<{
  searchParams: Promise<{ q?: string; page?: string }>;
}>;

export default async function CompetitionsPage({ searchParams }: CompetitionsPageProps) {
  const [user, dashboard, filters, teamSettings] = await Promise.all([
    requireUser(),
    getDashboard(),
    searchParams,
    getTeamSettings(),
  ]);
  if (isAdminView(user)) {
    redirect("/admin/competitions");
  }

  const query = (filters.q ?? "").trim().slice(0, 120);
  const requestedPage = Number(filters.page ?? "1");
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const directorySearch = new URLSearchParams({
    ...(query ? { query } : {}),
    page: String(page),
    page_size: "20",
  }).toString();
  const [team, teams] = teamSettings.is_team_open
    ? await Promise.all([getMyTeam(), getTeams(directorySearch)])
    : [null, null];

  return (
    <AppShell unreadCounts={dashboard.unread_counts} user={user}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / CAMPUS TEAMS
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">校内赛队伍中心</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        {teamSettings.is_team_open
          ? "无需等待管理员创建赛事。你可以直接创建队伍、使用邀请码加入，或由系统自动分配队伍。"
          : "管理员暂未开放学生组队。你可以先完善个人简介并浏览同学的技术方向。"}
      </p>
      <Link
        className="mt-5 inline-flex min-h-11 items-center border border-[var(--color-info)] px-5 text-sm text-[var(--color-info)]"
        href="/competitions/profiles"
      >
        浏览个人简介与组队邀请
      </Link>

      {teamSettings.is_team_open ? <TeamEntryPanel hasTeam={team !== null} /> : null}
      {teamSettings.is_team_open && team ? (
        <TeamManagementPanel initialTeam={team} currentUserId={user.id} />
      ) : null}
      {teamSettings.is_team_open && teams ? (
        <TeamDirectoryPanel initialTeams={teams} query={query} />
      ) : (
        <section className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 text-sm text-[var(--color-text-secondary)] shadow-[var(--shadow-card)] sm:p-6">
          组队开放后，本页将提供创建、邀请码加入、自动分配和队伍目录；目前可前往个人简介页填写简介并按技术组浏览同学。
        </section>
      )}
    </AppShell>
  );
}
