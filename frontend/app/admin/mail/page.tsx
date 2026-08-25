import { MailOutboxPanel } from "@/components/admin/mail-outbox-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getOutboxJobs, requireAdmin } from "@/lib/api/server";

export default async function AdminMailPage() {
  const [admin, jobs] = await Promise.all([requireAdmin(), getOutboxJobs()]);
  return (
    <AppShell user={admin}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / MAIL OUTBOX
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">邮件任务</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        这里只显示脱敏收件人、状态、尝试次数和错误摘要，不展示 payload、令牌或密文。只有已停止任务可以人工重试。
      </p>
      <MailOutboxPanel initialJobs={jobs.items} />
    </AppShell>
  );
}
