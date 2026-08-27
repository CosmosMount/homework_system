import Link from "next/link";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { KnowledgeAdminPanel } from "@/components/admin/knowledge-admin-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getAdminKnowledge, requireAdmin } from "@/lib/api/server";

export default async function AdminKnowledgePage() {
  const [admin, status] = await Promise.all([
    requireAdmin(),
    getAdminKnowledge(),
  ]);
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        actions={
          <Link
            className="inline-flex min-h-9 items-center rounded-lg border border-[var(--color-border)] px-3 text-sm text-[var(--color-info)] hover:bg-[var(--color-surface-hover)]"
            href="/knowledge"
          >
            打开培训文档
          </Link>
        }
        description="手动创建异步飞书知识库同步，查看学生当前版本和最近运行状态。同步失败不会覆盖成功快照。"
        eyebrow="ADMIN / KNOWLEDGE"
        title="培训文档同步"
      />
      <KnowledgeAdminPanel initialStatus={status} />
    </AppShell>
  );
}
