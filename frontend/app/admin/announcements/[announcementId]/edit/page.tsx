import { notFound } from "next/navigation";

import { AnnouncementEditor } from "@/components/admin/announcement-editor";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminAnnouncement,
  getCohorts,
  getDirections,
  requireAdmin,
} from "@/lib/api/server";

type EditAnnouncementPageProps = Readonly<{
  params: Promise<{ announcementId: string }>;
}>;

export default async function EditAnnouncementPage({
  params,
}: EditAnnouncementPageProps) {
  const { announcementId } = await params;
  const [admin, announcement, cohorts, directions] = await Promise.all([
    requireAdmin(),
    getAdminAnnouncement(announcementId),
    getCohorts(),
    getDirections(),
  ]);
  if (announcement === null) {
    notFound();
  }
  return (
    <AppShell user={admin}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / ANNOUNCEMENTS / EDIT
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">编辑通知</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        所有写入都携带 revision；发布、更新提醒和附件完成均使用幂等请求。
      </p>
      <AnnouncementEditor
        cohorts={cohorts}
        directions={directions}
        initialAnnouncement={announcement}
      />
    </AppShell>
  );
}
