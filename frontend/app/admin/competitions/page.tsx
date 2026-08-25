import Link from "next/link";

import { AppShell } from "@/components/layout/app-shell";
import { buttonLinkClassName } from "@/components/ui/form-controls";
import { getAdminCompetitions, requireAdmin } from "@/lib/api/server";
import {
  competitionStatusLabel,
  statusTagClass,
} from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

export default async function AdminCompetitionsPage() {
  const [admin, competitions] = await Promise.all([
    requireAdmin(),
    getAdminCompetitions(),
  ]);

  return (
    <AppShell user={admin}>
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
            ADMIN / COMPETITIONS
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">
            赛事管理
          </h1>
          <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
            管理赛事阶段、赛题、报名队伍、带原因纠错和团队私密评语。
          </p>
        </div>
        <Link
          className={buttonLinkClassName + " group shrink-0"}
          href="/admin/competitions/new"
        >
          <span aria-hidden="true" className="text-lg leading-none transition-transform group-hover:rotate-90">＋</span>
          <span>新建赛事</span>
        </Link>
      </div>

      <div className="mt-8 space-y-3">
        {competitions.items.map((competition) => (
          <Link
            className="block border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition hover:border-[var(--color-border-strong)]"
            href={"/admin/competitions/" + competition.id}
            key={competition.id}
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <span
                  className={
                    "border px-2 py-0.5 font-mono text-xs " +
                    statusTagClass(competition.status)
                  }
                >
                  {competitionStatusLabel(competition.status)}
                </span>
                <h2 className="mt-3 text-xl font-medium">{competition.name}</h2>
                <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                  队伍人数 {competition.min_team_size}–
                  {competition.max_team_size}
                </p>
              </div>
              <div className="text-right font-mono text-xs text-[var(--color-text-muted)]">
                <p>报名截止 {formatDateTime(competition.registration_end)}</p>
                <p className="mt-2">
                  提交结束 {formatDateTime(competition.submission_end)}
                </p>
              </div>
            </div>
          </Link>
        ))}
        {competitions.items.length === 0 ? (
          <p className="border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
            尚未创建赛事。
          </p>
        ) : null}
      </div>
    </AppShell>
  );
}
