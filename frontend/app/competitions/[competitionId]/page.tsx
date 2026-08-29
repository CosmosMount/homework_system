import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { SafeHtml } from "@/components/announcements/safe-html";
import { CompetitionRegistrationActions } from "@/components/competitions/registration-actions";
import { AppShell } from "@/components/layout/app-shell";
import {
  getCompetition,
  getDashboard,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";
import {
  competitionStatusLabel,
  statusTagClass,
} from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

type CompetitionDetailPageProps = Readonly<{
  params: Promise<{ competitionId: string }>;
}>;

export default async function CompetitionDetailPage({
  params,
}: CompetitionDetailPageProps) {
  const [{ competitionId }, user, dashboard] = await Promise.all([
    params,
    requireUser(),
    getDashboard(),
  ]);
  if (isAdminView(user)) {
    redirect("/admin/competitions/" + competitionId);
  }
  const competition = await getCompetition(competitionId);
  if (competition === null) {
    notFound();
  }

  return (
    <AppShell unreadCounts={dashboard.unread_counts} user={user}>
      <Link className="text-sm text-[var(--color-info)]" href="/competitions">
        ← 返回赛事列表
      </Link>
      <article className="mt-6">
        <div className="grid gap-6 border-b border-[var(--color-border)] pb-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div>
            <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
              COMPETITION / DETAIL
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              {competition.name}
            </h1>
            <span
              className={
                "mt-5 inline-block border px-2 py-1 font-mono text-xs " +
                statusTagClass(competition.status)
              }
            >
              {competitionStatusLabel(competition.status)}
            </span>
          </div>
          <dl className="space-y-3 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 text-sm">
            <div>
              <dt className="text-[var(--color-text-muted)]">报名窗口</dt>
              <dd className="mt-1">
                {formatDateTime(competition.registration_start)}
                <br />至 {formatDateTime(competition.registration_end)}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--color-text-muted)]">赛事时间</dt>
              <dd className="mt-1">
                {formatDateTime(competition.submission_start)}
                <br />至 {formatDateTime(competition.submission_end)}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--color-text-muted)]">队伍人数</dt>
              <dd className="mt-1">
                {competition.min_team_size}–{competition.max_team_size} 人
              </dd>
            </div>
          </dl>
        </div>

        <div className="mx-auto mt-8 max-w-4xl">
          <SafeHtml sanitizedHtml={competition.description_html} />
          {competition.rules_url ? (
            <p className="mt-6">
              <a
                className="text-[var(--color-info)] underline underline-offset-4"
                href={competition.rules_url}
                rel="noopener noreferrer"
                target="_blank"
              >
                打开赛事规则 ↗
              </a>
            </p>
          ) : null}
        </div>
      </article>

      <div className="mx-auto mt-10 max-w-4xl">
        <CompetitionRegistrationActions competition={competition} />
        <p className="mt-8 border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)] p-5 text-sm text-[var(--color-text-secondary)]">
          本赛事仅用于发布校内赛公告和完成报名组队，不设置赛题或作品提交。
        </p>
      </div>
    </AppShell>
  );
}
