import { UserAdminPanel } from "@/components/admin/user-admin-panel";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminUsers,
  getCohorts,
  getDirections,
  requireAdmin,
} from "@/lib/api/server";

export default async function AdminUsersPage() {
  const [admin, userPage, cohorts, directions] = await Promise.all([
    requireAdmin(),
    getAdminUsers(),
    getCohorts(),
    getDirections(),
  ]);
  return (
    <AppShell user={admin}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / USERS
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">用户管理</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        管理学生与管理员账号、可选届次和方向。系统没有注册审批；邮箱验证成功后学生会直接激活。
      </p>
      <UserAdminPanel
        cohorts={cohorts}
        directions={directions}
        initialUsers={userPage.items}
      />
    </AppShell>
  );
}
