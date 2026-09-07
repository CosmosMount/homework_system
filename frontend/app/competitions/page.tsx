import Link from "next/link";
import { redirect } from "next/navigation";

import { TeamEntryPanel } from "@/components/competitions/team-entry-panel";
import { TeamDirectoryPanel } from "@/components/competitions/team-directory-panel";
import { TeamManagementPanel } from "@/components/competitions/team-management-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getDashboard, getMyTeam, getTeams, requireUser } from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";

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
  const directorySearch = new URLSearchParams({
    ...(query ? { query } : {}),
    page: String(page),
    page_size: "20",
  }).toString();
  const [team, teams] = await Promise.all([
    getMyTeam(),
    getTeams(directorySearch),
  ]);

  return (
    <AppShell unreadCounts={dashboard.unread_counts} user={user}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / CAMPUS TEAMS
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">校内赛队伍中心</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        无需等待管理员创建赛事。你可以直接创建队伍、使用邀请码加入，或由系统自动分配队伍。
      </p>
      <Link
        className="mt-5 inline-flex min-h-11 items-center border border-[var(--color-info)] px-5 text-sm text-[var(--color-info)]"
        href="/competitions/profiles"
      >
        浏览个人简介与组队邀请
      </Link>

      <TeamEntryPanel hasTeam={team !== null} />
      {team ? (
        <TeamManagementPanel initialTeam={team} currentUserId={user.id} />
      ) : null}
      <TeamDirectoryPanel initialTeams={teams} query={query} />
    </AppShell>
  );
}
