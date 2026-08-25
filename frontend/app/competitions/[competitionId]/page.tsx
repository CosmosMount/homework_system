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
import {
  competitionStatusLabel,
  statusTagClass,
} from "@/lib/competition-labels";
import { formatDateTime, formatFileSize } from "@/lib/format";

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
  if (user.role === "admin") {
    redirect("/admin/competitions/" + competitionId);
  }
  const competition = await getCompetition(competitionId);
  if (competition === null) {
    notFound();
  }

  return (
    <AppShell unreadCount={dashboard.unread_count} user={user}>
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
              <dt className="text-[var(--color-text-muted)]">提交窗口</dt>
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

        <section className="mt-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold">赛题 / 交付项</h2>
              <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                各赛题截止独立；正式版本不可修改，当前团队成员均可查看团队评语。
              </p>
            </div>
            <span className="font-mono text-xs text-[var(--color-text-muted)]">
              {competition.tasks.length} tasks
            </span>
          </div>
          {competition.tasks.length ? (
            <div className="mt-4 space-y-3">
              {competition.tasks.map((task) => (
                <Link
                  className="block border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
                  href={
                    "/competitions/" +
                    competition.id +
                    "/tasks/" +
                    task.id
                  }
                  key={task.id}
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="font-medium">{task.title}</p>
                      <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                        {task.allowed_extensions.join(", ")} ·{" "}
                        {formatFileSize(task.max_total_bytes)}
                      </p>
                      {task.submission_id ? (
                        <span className="mt-3 inline-block border border-[var(--color-success)] px-2 py-0.5 font-mono text-xs text-[var(--color-success)]">
                          已有团队正式版本
                        </span>
                      ) : null}
                    </div>
                    <time
                      className="font-mono text-xs text-[var(--color-text-muted)]"
                      dateTime={task.deadline}
                    >
                      截止 {formatDateTime(task.deadline)}
                    </time>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <p className="mt-4 border border-dashed border-[var(--color-border-strong)] p-6 text-center text-[var(--color-text-muted)]">
              尚未配置赛题。
            </p>
          )}
        </section>
      </div>
    </AppShell>
  );
}
