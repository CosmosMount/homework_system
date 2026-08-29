import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AttachmentDownloadButton } from "@/components/announcements/announcement-actions";
import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import {
  getDashboard,
  getSubmission,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";
import { formatDateTime, formatFileSize } from "@/lib/format";

type SubmissionPageProps = Readonly<{
  params: Promise<{ assignmentId: string; submissionId: string }>;
}>;

export default async function SubmissionPage({
  params,
}: SubmissionPageProps) {
  const [{ assignmentId, submissionId }, user, dashboard] = await Promise.all([
    params,
    requireUser(),
    getDashboard(),
  ]);
  if (isAdminView(user)) {
    redirect("/admin/submissions/" + submissionId);
  }
  const submission = await getSubmission(submissionId);
  if (submission === null || submission.assignment_id !== assignmentId) {
    notFound();
  }

  return (
    <AppShell unreadCounts={dashboard.unread_counts} user={user}>
      <Link
        className="text-sm text-[var(--color-info)]"
        href={"/assignments/" + assignmentId}
      >
        ← 返回作业详情
      </Link>
      <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
            SUBMISSION / HISTORY
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">
            正式版本历史
          </h1>
          <p className="mt-3 text-[var(--color-text-secondary)]">
            每个版本创建后不可修改或删除；评语只对你和管理员可见。
          </p>
        </div>
        <span className="font-mono text-xs text-[var(--color-text-muted)]">
          {submission.versions.length} versions
        </span>
      </div>

      <div className="mt-8 space-y-6">
        {submission.versions.map((version) => (
          <article
            className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6"
            id={"version-" + version.id}
            key={version.id}
          >
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--color-border)] pb-4">
              <div>
                <h2 className="text-2xl font-semibold">
                  v{version.version_number}
                  {version.id === submission.latest_version_id ? (
                    <span className="ml-3 align-middle font-mono text-xs text-[var(--color-accent-hover)]">
                      LATEST
                    </span>
                  ) : null}
                </h2>
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
                <h3 className="text-lg font-medium">附件</h3>
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
                          {attachment.media_type} ·{" "}
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
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-lg font-semibold">私密评语</h3>
                  <span className="font-mono text-xs text-[var(--color-text-muted)]">
                    revision {version.feedback.revision}
                  </span>
                </div>
                <div className="mt-4">
                  <SafeHtml sanitizedHtml={version.feedback.body_html} />
                </div>
                <p className="mt-4 text-xs text-[var(--color-text-muted)]">
                  更新于 {formatDateTime(version.feedback.updated_at)}
                </p>
              </section>
            ) : (
              <p className="mt-6 text-sm text-[var(--color-text-muted)]">
                该版本尚无私密评语。
              </p>
            )}
          </article>
        ))}
      </div>
    </AppShell>
  );
}
