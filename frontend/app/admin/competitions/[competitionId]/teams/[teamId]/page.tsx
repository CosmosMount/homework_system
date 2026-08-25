import Link from "next/link";
import { notFound } from "next/navigation";

import { AdminTeamCorrectionPanel } from "@/components/admin/team-correction-panel";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminTeam,
  getAdminUsers,
  requireAdmin,
} from "@/lib/api/server";

type AdminTeamPageProps = Readonly<{
  params: Promise<{ competitionId: string; teamId: string }>;
}>;

export default async function AdminTeamPage({
  params,
}: AdminTeamPageProps) {
  const { competitionId, teamId } = await params;
  const [admin, team, users] = await Promise.all([
    requireAdmin(),
    getAdminTeam(teamId),
    getAdminUsers(),
  ]);
  if (team === null || team.competition_id !== competitionId) {
    notFound();
  }

  return (
    <AppShell user={admin}>
      <Link
        className="text-sm text-[var(--color-info)]"
        href={"/admin/competitions/" + competitionId}
      >
        ← 返回赛事管理
      </Link>
      <p className="mt-6 font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / COMPETITIONS / TEAM
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">队伍详情</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        补录、移除、队长变更、人数豁免和取消资格都必须填写原因并进入审计。
      </p>
      <AdminTeamCorrectionPanel initialTeam={team} users={users.items} />
    </AppShell>
  );
}
