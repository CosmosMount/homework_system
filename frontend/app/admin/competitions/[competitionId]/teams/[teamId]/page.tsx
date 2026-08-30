import { notFound } from "next/navigation";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
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
      <AdminPageHeader
        backHref="/admin/competitions"
        backLabel="返回校内赛"
        eyebrow="ADMIN / CAMPUS COMPETITION / TEAM"
        title="队伍详情"
        description="补录、移除、队长变更、人数豁免、取消资格和删除都必须填写原因并进入审计。"
      />
      <AdminTeamCorrectionPanel initialTeam={team} users={users.items} />
    </AppShell>
  );
}
