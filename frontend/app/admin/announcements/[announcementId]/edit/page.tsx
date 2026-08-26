import { notFound } from "next/navigation";

import { AdminPageHeader } from "@/components/admin/admin-page-header";

import { AnnouncementEditor } from "@/components/admin/announcement-editor";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminAnnouncement,
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
  const [admin, announcement, directions] = await Promise.all([
    requireAdmin(),
    getAdminAnnouncement(announcementId),
    getDirections(),
  ]);
  if (announcement === null) {
    notFound();
  }
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/announcements"
        backLabel="返回通知管理"
        eyebrow="ADMIN / ANNOUNCEMENTS / EDIT"
        title="编辑通知"
        description="所有写入都携带 revision；发布、更新提醒和附件完成均使用幂等请求。"
      />
      <AnnouncementEditor
        directions={directions}
        initialAnnouncement={announcement}
      />
    </AppShell>
  );
}
