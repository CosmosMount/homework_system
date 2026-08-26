import { notFound } from "next/navigation";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { CompetitionEditor } from "@/components/admin/competition-editor";
import { AdminCompetitionRegistrationPanel } from "@/components/admin/competition-registration-panel";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminCompetition,
  getAdminCompetitionRegistrations,
  getAdminCompetitionTeams,
  requireAdmin,
} from "@/lib/api/server";

type AdminCompetitionPageProps = Readonly<{
  params: Promise<{ competitionId: string }>;
}>;

export default async function AdminCompetitionPage({
  params,
}: AdminCompetitionPageProps) {
  const { competitionId } = await params;
  const [admin, competition, teams, registrations] = await Promise.all([
    requireAdmin(),
    getAdminCompetition(competitionId),
    getAdminCompetitionTeams(competitionId),
    getAdminCompetitionRegistrations(competitionId),
  ]);
  if (competition === null) {
    notFound();
  }

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/competitions"
        backLabel="返回校内赛"
        eyebrow="ADMIN / CAMPUS COMPETITION / DETAIL"
        title="校内赛设置"
        description="revision 防止并发覆盖；锁队、人数失效和管理员纠错均由后端事务与审计保证。"
      />
      <CompetitionEditor
        initialCompetition={competition}
        initialTeams={teams.items}
      />
      <AdminCompetitionRegistrationPanel
        archived={competition.status === "archived"}
        competitionId={competition.id}
        initialRegistrations={registrations.items}
      />
    </AppShell>
  );
}
