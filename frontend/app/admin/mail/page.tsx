import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { MailOutboxPanel } from "@/components/admin/mail-outbox-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getOutboxJobs, requireAdmin } from "@/lib/api/server";

export default async function AdminMailPage() {
  const [admin, jobs] = await Promise.all([requireAdmin(), getOutboxJobs()]);
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / MAIL OUTBOX"
        title="邮件任务"
        description="这里只显示脱敏收件人、状态、尝试次数和错误摘要，不展示 payload、令牌或密文。只有已停止任务可以人工重试。"
      />
      <MailOutboxPanel initialJobs={jobs.items} />
    </AppShell>
  );
}
