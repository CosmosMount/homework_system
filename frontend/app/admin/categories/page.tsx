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
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / DIRECTIONS
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">方向设置</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        技术方向是登录后的可选分类，不是账号激活条件。停用方向不会修改历史记录。
      </p>
      <CategoryAdminPanel initialDirections={directions} />
    </AppShell>
  );
}
