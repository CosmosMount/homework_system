import { redirect } from "next/navigation";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { CompetitionEditor } from "@/components/admin/competition-editor";
import { AppShell } from "@/components/layout/app-shell";
import { getAdminCompetitions, requireAdmin } from "@/lib/api/server";

export default async function NewCompetitionPage() {
  const [admin, competitions] = await Promise.all([
    requireAdmin(),
    getAdminCompetitions(),
  ]);
  if (competitions.items.some((item) => item.status !== "archived")) {
    redirect("/admin/competitions");
  }
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/competitions"
        backLabel="返回校内赛"
        eyebrow="ADMIN / CAMPUS COMPETITION / SETUP"
        title="配置校内赛"
        description="首次配置校内赛公告、报名时间和组队人数；系统只允许一条未归档校内赛。"
      />
      <CompetitionEditor initialCompetition={null} initialTeams={[]} />
    </AppShell>
  );
}
