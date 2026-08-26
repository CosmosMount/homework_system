import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditLogPanel } from "@/components/admin/audit-log-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getAuditLogs, requireAdmin } from "@/lib/api/server";

export default async function AdminAuditPage() {
  const [admin, logs] = await Promise.all([requireAdmin(), getAuditLogs()]);
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / AUDIT"
        title="审计日志"
        description="按动作、目标和请求 ID 检索最近记录。变更摘要不包含密码、令牌、Cookie 或邮件密文。"
      />
      <AuditLogPanel initialLogs={logs.items} />
    </AppShell>
  );
}
