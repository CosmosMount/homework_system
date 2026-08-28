import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { IntentionAdminPanel } from "@/components/admin/intention-admin-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getAdminIntentions, requireAdmin } from "@/lib/api/server";

export default async function AdminIntentionsPage() {
  const [admin, surveys] = await Promise.all([requireAdmin(), getAdminIntentions()]);
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        description="创建包含多道单选或多选题的问卷，限制提交次数，并查看实名提交名单与分题统计。"
        eyebrow="ADMIN / QUESTIONNAIRES"
        title="问卷管理"
      />
      <IntentionAdminPanel initialSurveys={surveys.items} />
    </AppShell>
  );
}
