import Link from "next/link";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AnnouncementListPanel } from "@/components/admin/announcement-list-panel";
import { AppShell } from "@/components/layout/app-shell";
import { commandLinkClassName } from "@/components/ui/form-controls";

import { getAdminAnnouncements, requireAdmin } from "@/lib/api/server";

export default async function AdminAnnouncementsPage() {
  const [admin, announcements] = await Promise.all([
    requireAdmin(),
    getAdminAnnouncements(),
  ]);
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / ANNOUNCEMENTS"
        title="通知管理"
        description="创建草稿、配置受众、安排发布时间，并查看预计与实际接收快照。"
        actions={
          <Link
            className={commandLinkClassName + " group"}
            href="/admin/announcements/new"
          >
            <span aria-hidden="true" className="text-base leading-none transition-transform group-hover:rotate-90">＋</span>
            <span>新建通知</span>
          </Link>
        }
      />
      <AnnouncementListPanel initialAnnouncements={announcements.items} />
    </AppShell>
  );
}
