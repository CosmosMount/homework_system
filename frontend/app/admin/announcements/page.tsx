import Link from "next/link";

import { AnnouncementListPanel } from "@/components/admin/announcement-list-panel";
import { AppShell } from "@/components/layout/app-shell";
import { buttonLinkClassName } from "@/components/ui/form-controls";
import { getAdminAnnouncements, requireAdmin } from "@/lib/api/server";

export default async function AdminAnnouncementsPage() {
  const [admin, announcements] = await Promise.all([
    requireAdmin(),
    getAdminAnnouncements(),
  ]);
  return (
    <AppShell user={admin}>
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
            ADMIN / ANNOUNCEMENTS
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">通知管理</h1>
          <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
            创建草稿、配置受众、安排发布时间，并查看预计与实际接收快照。
          </p>
        </div>
        <Link
          className={buttonLinkClassName + " group shrink-0"}
          href="/admin/announcements/new"
        >
          <span aria-hidden="true" className="text-lg leading-none transition-transform group-hover:rotate-90">＋</span>
          <span>新建通知</span>
        </Link>
      </div>
      <AnnouncementListPanel initialAnnouncements={announcements.items} />
    </AppShell>
  );
}
