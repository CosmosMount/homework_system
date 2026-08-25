import { CategoryAdminPanel } from "@/components/admin/category-admin-panel";
import { AppShell } from "@/components/layout/app-shell";
import {
  getCohorts,
  getDirections,
  requireAdmin,
} from "@/lib/api/server";

export default async function AdminCategoriesPage() {
  const [admin, cohorts, directions] = await Promise.all([
    requireAdmin(),
    getCohorts(),
    getDirections(),
  ]);
  return (
    <AppShell user={admin}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / CLASSIFICATION
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">届次与方向</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        届次和方向是登录后的可选分类，不是账号激活条件。停用分类不会修改历史记录。
      </p>
      <CategoryAdminPanel
        initialCohorts={cohorts}
        initialDirections={directions}
      />
    </AppShell>
  );
}
