import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AttachmentDownloadButton } from "@/components/announcements/announcement-actions";
import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import {
  getDashboard,
  getExcellentSubmission,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";
import { formatDateTime, formatFileSize } from "@/lib/format";

type ExcellentSubmissionPageProps = Readonly<{
  params: Promise<{ assignmentId: string; versionId: string }>;
}>;

export default async function ExcellentSubmissionPage({
  params,
}: ExcellentSubmissionPageProps) {
  const [{ assignmentId, versionId }, user, dashboard] = await Promise.all([
    params,
    requireUser(),
    getDashboard(),
  ]);
  if (isAdminView(user)) {
    redirect("/admin/assignments/" + assignmentId + "/edit");
  }
  const version = await getExcellentSubmission(assignmentId, versionId);
  if (version === null) {
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
      <article className="mx-auto mt-6 max-w-4xl">
        <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
          EXCELLENT SUBMISSION / SOURCE VERSION
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">
          {version.assignment_title}
        </h1>
        <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-sm text-[var(--color-text-secondary)]">
          <span>{version.author_name}</span>
          <span>版本 v{version.version_number}</span>
          <time dateTime={version.submitted_at}>
            提交于 {formatDateTime(version.submitted_at)}
          </time>
        </div>
        <p className="mt-5 border-l-2 border-[var(--color-info)] px-4 text-sm text-[var(--color-text-muted)]">
          此页面只展示被标记的源版本，不包含作者的私密评语或其他历史版本。
        </p>

        {version.text_html ? (
          <div className="mt-8">
            <SafeHtml sanitizedHtml={version.text_html} />
          </div>
        ) : null}
        {version.external_url ? (
          <p className="mt-7">
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
          <section className="mt-10 border-t border-[var(--color-border)] pt-6">
            <h2 className="text-xl font-semibold">附件</h2>
            <div className="mt-4 space-y-3">
              {version.attachments.map((attachment) => (
                <div
                  className="flex flex-wrap items-center justify-between gap-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
                  key={attachment.id}
                >
                  <div>
                    <p className="font-medium">{attachment.file_name}</p>
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
      </article>
    </AppShell>
  );
}
