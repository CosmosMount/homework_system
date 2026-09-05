import { notFound } from "next/navigation";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AdminTeamCorrectionPanel } from "@/components/admin/team-correction-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getAdminTeam, getAdminUsers, requireAdmin } from "@/lib/api/server";

type AdminTeamPageProps = Readonly<{
  params: Promise<{ competitionId: string }>;
}>;

export default async function AdminTeamPage({ params }: AdminTeamPageProps) {
  const { competitionId: teamId } = await params;
  const [admin, team, users] = await Promise.all([
    requireAdmin(),
    getAdminTeam(teamId),
    getAdminUsers(),
  ]);
  if (team === null) {
    notFound();
  }

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/competitions"
        backLabel="返回队伍目录"
        eyebrow="ADMIN / CAMPUS TEAMS / DETAIL"
        title="队伍详情"
        description="管理员补录、移除、队长变更和删除都必须填写原因并进入审计。"
      />
      <AdminTeamCorrectionPanel initialTeam={team} users={users.items} />
    </AppShell>
  );
}
