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
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / ANNOUNCEMENTS / NEW
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">新建通知</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        首次保存会建立草稿上下文；之后即可上传并绑定附件。
      </p>
      <AnnouncementEditor
        directions={directions}
        initialAnnouncement={null}
      />
    </AppShell>
  );
}
