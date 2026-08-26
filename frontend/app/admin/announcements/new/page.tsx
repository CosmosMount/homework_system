import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AnnouncementEditor } from "@/components/admin/announcement-editor";
import { AppShell } from "@/components/layout/app-shell";
import { getDirections, requireAdmin } from "@/lib/api/server";

export default async function NewAnnouncementPage() {
  const [admin, directions] = await Promise.all([
    requireAdmin(),
    getDirections(),
  ]);
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/announcements"
        backLabel="返回通知管理"
        eyebrow="ADMIN / ANNOUNCEMENTS / NEW"
        title="新建通知"
        description="首次保存会建立草稿上下文；之后即可上传并绑定附件。"
      />
      <AnnouncementEditor
        directions={directions}
        initialAnnouncement={null}
      />
    </AppShell>
  );
}
