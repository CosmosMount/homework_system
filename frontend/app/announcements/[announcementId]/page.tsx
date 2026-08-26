import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import {
  AttachmentDownloadButton,
  MarkAnnouncementRead,
} from "@/components/announcements/announcement-actions";
import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import { getAnnouncement, getDashboard, requireUser } from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";
import { formatDateTime, formatFileSize } from "@/lib/format";

type AnnouncementDetailPageProps = Readonly<{
  params: Promise<{ announcementId: string }>;
}>;

export default async function AnnouncementDetailPage({
  params,
}: AnnouncementDetailPageProps) {
  const [{ announcementId }, user, dashboard] = await Promise.all([
    params,
    requireUser(),
    getDashboard(),
  ]);
  if (isAdminView(user)) {
    redirect("/admin/announcements/" + announcementId + "/edit");
  }
  const announcement = await getAnnouncement(announcementId);
  if (announcement === null) {
    notFound();
  }

  return (
    <AppShell unreadCount={dashboard.unread_count} user={user}>
      <Link className="text-sm text-[var(--color-info)]" href="/announcements">
        ← 返回通知中心
      </Link>
      <article className="mt-6">
        <div className="border-b border-[var(--color-border)] pb-7">
          <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
            ANNOUNCEMENT / DETAIL
          </p>
          <h1 className="mt-3 max-w-4xl text-3xl font-semibold tracking-tight sm:text-4xl">
            {announcement.title}
          </h1>
          <p className="mt-4 max-w-3xl text-[var(--color-text-secondary)]">
            {announcement.summary}
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3 text-xs text-[var(--color-text-muted)]">
            <time dateTime={announcement.published_at}>
              发布于 {formatDateTime(announcement.published_at)}
            </time>
            <span>{announcement.audience_description}</span>
            <MarkAnnouncementRead notificationIds={announcement.notification_ids} />
          </div>
        </div>

        <div className="mx-auto mt-8 max-w-4xl">
          <SafeHtml sanitizedHtml={announcement.body_html} />
        </div>

        {announcement.attachments.length ? (
          <section className="mx-auto mt-12 max-w-4xl border-t border-[var(--color-border)] pt-7">
            <h2 className="text-xl font-semibold">附件</h2>
            <div className="mt-4 space-y-3">
              {announcement.attachments.map((attachment) => (
                <div
                  className="flex flex-wrap items-center justify-between gap-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
                  key={attachment.id}
                >
                  <div>
                    <p className="font-medium">{attachment.file_name}</p>
                    <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                      {attachment.media_type} · {formatFileSize(attachment.size_bytes)}
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
