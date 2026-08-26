import Link from "next/link";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AppShell } from "@/components/layout/app-shell";
import { commandLinkClassName } from "@/components/ui/form-controls";
import {
  getAdminCompetitionTeams,
  getAdminCompetitions,
  requireAdmin,
} from "@/lib/api/server";
import {
  competitionStatusLabel,
  statusTagClass,
  teamStatusLabel,
} from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

export default async function AdminCompetitionsPage() {
  const [admin, competitions] = await Promise.all([
    requireAdmin(),
    getAdminCompetitions(),
  ]);
  const currentCompetition =
    competitions.items.find((item) => item.status !== "archived") ?? null;
  const teams = currentCompetition
    ? await getAdminCompetitionTeams(currentCompetition.id)
    : { items: [], total: 0 };

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / CAMPUS COMPETITION"
        title="校内赛"
        description="统一管理校内赛公告、报名状态和参赛队伍。系统只保留一条当前校内赛，不再创建多个赛事。"
        actions={
          currentCompetition ? (
            <Link
              className={commandLinkClassName}
              href={"/admin/competitions/" + currentCompetition.id}
            >
              管理公告
            </Link>
          ) : null
        }
      />

      {currentCompetition ? (
        <section className="overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-card)]">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--color-border)] p-5 sm:p-6">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={
                    "border px-2 py-0.5 font-mono text-xs " +
                    statusTagClass(currentCompetition.status)
                  }
                >
                  {competitionStatusLabel(currentCompetition.status)}
                </span>
                <span className="rounded-full bg-[var(--color-surface-hover)] px-2.5 py-1 text-xs text-[var(--color-text-muted)]">
                  当前校内赛
                </span>
              </div>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight">
                {currentCompetition.name}
              </h2>
              <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                报名截止 {formatDateTime(currentCompetition.registration_end)}
                <span className="mx-2 text-[var(--color-border-strong)]">·</span>
                队伍人数 {currentCompetition.min_team_size}–
                {currentCompetition.max_team_size}
              </p>
            </div>
            <div className="text-right font-mono text-xs text-[var(--color-text-muted)]">
              <p>赛事结束</p>
              <p className="mt-1">{formatDateTime(currentCompetition.submission_end)}</p>
            </div>
          </div>

          <div className="p-5 sm:p-6">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-medium tracking-[0.14em] text-[var(--color-text-muted)]">
                  TEAMS
                </p>
                <h2 className="mt-1 text-xl font-semibold">参赛队伍</h2>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)]">
                共 {teams.total} 支队伍
              </p>
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {teams.items.map((team) => (
                <Link
                  className="group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 transition hover:-translate-y-0.5 hover:border-[var(--color-accent)] hover:shadow-[var(--shadow-card)]"
                  href={
                    "/admin/competitions/" +
                    team.competition_id +
                    "/teams/" +
                    team.id
                  }
                  key={team.id}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium group-hover:text-[var(--color-accent-hover)]">
                        {team.name}
                      </p>
                      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
                        {team.member_count} 人 · {teamStatusLabel(team.status)}
                      </p>
                    </div>
                    <span className="font-mono text-xs text-[var(--color-info)]">
                      查看 →
                    </span>
                  </div>
                  {team.min_size_waived ? (
                    <p className="mt-3 text-xs text-[var(--color-warning)]">
                      已豁免最小人数
                    </p>
                  ) : null}
                </Link>
              ))}
            </div>
            {teams.items.length === 0 ? (
              <p className="mt-5 rounded-xl border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
                当前还没有参赛队伍。
              </p>
            ) : null}
          </div>
        </section>
      ) : (
        <section className="rounded-2xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)] p-10 text-center">
          <h2 className="text-xl font-semibold">尚未配置校内赛</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            当前没有可管理的未归档校内赛。
          </p>
        </section>
      )}
    </AppShell>
  );
}
