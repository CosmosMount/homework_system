import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { CategoryAdminPanel } from "@/components/admin/category-admin-panel";
import { AppShell } from "@/components/layout/app-shell";
import { getDirections, requireAdmin } from "@/lib/api/server";

export default async function AdminCategoriesPage() {
  const [admin, directions] = await Promise.all([
    requireAdmin(),
    getDirections(),
  ]);
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / DIRECTIONS"
        title="方向设置"
        description="技术方向是登录后的可选分类，不是账号激活条件。停用方向不会修改历史记录。"
      />
      <CategoryAdminPanel initialDirections={directions} />
    </AppShell>
  );
}
