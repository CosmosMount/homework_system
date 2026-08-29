import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { TeamManagementPanel } from "@/components/competitions/team-management-panel";
import { AppShell } from "@/components/layout/app-shell";
import {
  getCompetition,
  getCompetitionTeam,
  getDashboard,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";

type CompetitionTeamPageProps = Readonly<{
  params: Promise<{ competitionId: string }>;
}>;

export default async function CompetitionTeamPage({
  params,
}: CompetitionTeamPageProps) {
  const [{ competitionId }, user, dashboard] = await Promise.all([
    params,
    requireUser(),
    getDashboard(),
  ]);
  if (isAdminView(user)) {
    redirect("/admin/competitions/" + competitionId);
  }
  const [competition, team] = await Promise.all([
    getCompetition(competitionId),
    getCompetitionTeam(competitionId),
  ]);
  if (competition === null || team === null) {
    notFound();
  }

  return (
    <AppShell unreadCounts={dashboard.unread_counts} user={user}>
      <Link
        className="text-sm text-[var(--color-info)]"
        href={"/competitions/" + competitionId}
      >
        ← 返回赛事详情
      </Link>
      <p className="mt-6 font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        COMPETITION / MY TEAM
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">我的队伍</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        {competition.name}。报名结束后成员关系自动锁定；管理员纠错会保留原因和审计。
      </p>
      <TeamManagementPanel currentUserId={user.id} initialTeam={team} />
    </AppShell>
  );
}
