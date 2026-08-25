import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AttachmentDownloadButton } from "@/components/announcements/announcement-actions";
import { SafeHtml } from "@/components/announcements/safe-html";
import { CompetitionSubmissionForm } from "@/components/assignments/submission-form";
import { AppShell } from "@/components/layout/app-shell";
import {
  getCompetition,
  getCompetitionSubmission,
  getCompetitionTask,
  getCompetitionTeam,
  getDashboard,
  requireUser,
} from "@/lib/api/server";
import { formatDateTime, formatFileSize } from "@/lib/format";

type CompetitionTaskPageProps = Readonly<{
  params: Promise<{ competitionId: string; taskId: string }>;
}>;

export default async function CompetitionTaskPage({
  params,
}: CompetitionTaskPageProps) {
  const [{ competitionId, taskId }, user, dashboard] = await Promise.all([
    params,
    requireUser(),
    getDashboard(),
  ]);
  if (user.role === "admin") {
    redirect("/admin/competitions/" + competitionId);
  }
  const [competition, task, team, submission] = await Promise.all([
    getCompetition(competitionId),
    getCompetitionTask(competitionId, taskId),
    getCompetitionTeam(competitionId),
    getCompetitionSubmission(competitionId, taskId),
  ]);
  if (competition === null || task === null) {
    notFound();
  }
  const isCaptain = team?.captain_user_id === user.id;
  const beforeTaskDeadline = new Date().getTime() < new Date(task.deadline).getTime();
  const canSubmit = Boolean(
    team?.can_submit && isCaptain && beforeTaskDeadline,
  );

  return (
    <AppShell unreadCount={dashboard.unread_count} user={user}>
      <Link
        className="text-sm text-[var(--color-info)]"
        href={"/competitions/" + competitionId}
      >
        ← 返回赛事详情
      </Link>
      <article className="mt-6">
        <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
          COMPETITION / TASK
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">
          {task.title}
        </h1>
        <p className="mt-3 text-sm text-[var(--color-text-secondary)]">
          {competition.name} · 截止 {formatDateTime(task.deadline)}
        </p>
        <div className="mx-auto mt-8 max-w-4xl">
          <SafeHtml sanitizedHtml={task.description_html} />
          {task.resource_url ? (
            <p className="mt-6">
              <a
                className="text-[var(--color-info)] underline underline-offset-4"
                href={task.resource_url}
                rel="noopener noreferrer"
                target="_blank"
              >
                打开赛题资料 ↗
              </a>
            </p>
          ) : null}
          <p className="mt-6 border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm text-[var(--color-text-secondary)]">
            允许扩展名：{task.allowed_extensions.join(", ")}；单版本附件上限{" "}
            {formatFileSize(task.max_total_bytes)}。
          </p>
        </div>
      </article>

      <div className="mx-auto mt-10 max-w-4xl">
        {submission ? (
          <section>
            <h2 className="text-2xl font-semibold">团队正式版本</h2>
            <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
              当前团队成员可查看全部不可变版本和私密评语。
            </p>
            <div className="mt-5 space-y-6">
              {submission.versions.map((version) => (
                <article
                  className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6"
                  id={"version-" + version.id}
                  key={version.id}
                >
                  <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--color-border)] pb-4">
                    <div>
                      <h3 className="text-2xl font-semibold">
                        v{version.version_number}
                        {version.id === submission.latest_version_id ? (
                          <span className="ml-3 align-middle font-mono text-xs text-[var(--color-accent-hover)]">
                            LATEST
                          </span>
                        ) : null}
                      </h3>
                      <time
                        className="mt-2 block text-xs text-[var(--color-text-muted)]"
                        dateTime={version.submitted_at}
                      >
                        {formatDateTime(version.submitted_at)}
                      </time>
                    </div>
                    <span className="font-mono text-xs text-[var(--color-text-muted)]">
                      {formatFileSize(version.total_file_bytes)}
                    </span>
                  </div>
                  {version.text_html ? (
                    <div className="mt-6">
                      <SafeHtml sanitizedHtml={version.text_html} />
                    </div>
                  ) : null}
                  {version.external_url ? (
                    <p className="mt-6">
                      <a
                        className="text-[var(--color-info)] underline underline-offset-4"
                        href={version.external_url}
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        打开外部提交链接 ↗
                      </a>
                    </p>
                  ) : null}
                  {version.attachments.length ? (
                    <section className="mt-6">
                      <h4 className="font-medium">附件</h4>
                      <div className="mt-3 space-y-2">
                        {version.attachments.map((attachment) => (
                          <div
                            className="flex flex-wrap items-center justify-between gap-4 border border-[var(--color-border)] p-3"
                            key={attachment.id}
                          >
                            <div>
                              <p className="text-sm font-medium">
                                {attachment.file_name}
                              </p>
                              <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                                {formatFileSize(attachment.size_bytes)}
                              </p>
                            </div>
                            <AttachmentDownloadButton fileId={attachment.id} />
                          </div>
                        ))}
                      </div>
                    </section>
                  ) : null}
                  {version.feedback ? (
                    <section className="mt-7 border-l-2 border-[var(--color-info)] bg-[var(--color-bg)] p-5">
                      <h4 className="text-lg font-semibold">团队私密评语</h4>
                      <div className="mt-4">
                        <SafeHtml
                          sanitizedHtml={version.feedback.body_html}
                        />
                      </div>
                      <p className="mt-4 text-xs text-[var(--color-text-muted)]">
                        更新于 {formatDateTime(version.feedback.updated_at)}
                      </p>
                    </section>
                  ) : (
                    <p className="mt-6 text-sm text-[var(--color-text-muted)]">
                      该版本尚无团队私密评语。
                    </p>
                  )}
                </article>
              ))}
            </div>
          </section>
        ) : (
          <p className="border border-dashed border-[var(--color-border-strong)] p-6 text-[var(--color-text-muted)]">
            当前团队尚未创建正式版本。
          </p>
        )}

        {canSubmit ? (
          <CompetitionSubmissionForm
            allowedExtensions={task.allowed_extensions}
            competitionId={competitionId}
            maxTotalBytes={task.max_total_bytes}
            taskId={taskId}
          />
        ) : (
          <p className="mt-8 border border-dashed border-[var(--color-border-strong)] p-6 text-[var(--color-text-muted)]">
            {team === null
              ? "你尚未加入本赛事队伍。"
              : !isCaptain
                ? "只有当前队长可以代表团队创建正式版本；你仍可查看团队历史版本和评语。"
                : "当前队伍、赛事阶段或赛题截止状态不允许创建新版本。"}
          </p>
        )}
      </div>
    </AppShell>
  );
}
