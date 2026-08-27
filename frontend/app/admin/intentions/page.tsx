import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { IntentionAdminPanel } from "@/components/admin/intention-admin-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getAdminIntentions, requireAdmin } from "@/lib/api/server";

export default async function AdminIntentionsPage() {
  const [admin, surveys] = await Promise.all([requireAdmin(), getAdminIntentions()]);
  return <AppShell user={admin}><AdminPageHeader eyebrow="ADMIN / INTENTIONS" title="学生意向调查" description="创建单选或多选意向调查，查看匿名汇总，并生成移动端填写二维码。" /><IntentionAdminPanel initialSurveys={surveys.items} /></AppShell>;
}
