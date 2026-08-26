import { CompetitionEditor } from "@/components/admin/competition-editor";
import { AppShell } from "@/components/layout/app-shell";
import { requireAdmin } from "@/lib/api/server";

export default async function NewCompetitionPage() {
  const admin = await requireAdmin();
  return (
    <AppShell user={admin}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / COMPETITIONS / NEW
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">新建赛事</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        填写公告、报名时间和组队人数后即可发布；赛事阶段只能单向推进。
      </p>
      <CompetitionEditor initialCompetition={null} initialTeams={[]} />
    </AppShell>
  );
}
