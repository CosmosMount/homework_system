import { AuditLogPanel } from "@/components/admin/audit-log-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getAuditLogs, requireAdmin } from "@/lib/api/server";

export default async function AdminAuditPage() {
  const [admin, logs] = await Promise.all([requireAdmin(), getAuditLogs()]);
  return (
    <AppShell user={admin}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / AUDIT
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">审计日志</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        按动作、目标和请求 ID 检索最近记录。变更摘要不包含密码、令牌、Cookie 或邮件密文。
      </p>
      <AuditLogPanel initialLogs={logs.items} />
    </AppShell>
  );
}
