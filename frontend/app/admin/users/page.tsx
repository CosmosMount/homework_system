import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { UserAdminPanel } from "@/components/admin/user-admin-panel";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminUsers,
  getDirections,
  requireAdmin,
} from "@/lib/api/server";

export default async function AdminUsersPage() {
  const [admin, userPage, directions] = await Promise.all([
    requireAdmin(),
    getAdminUsers(),
    getDirections(),
  ]);
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / USERS"
        title="用户管理"
        description="管理学生与管理员账号及技术方向。系统没有注册审批；邮箱验证成功后学生会直接激活。"
      />
      <UserAdminPanel
        directions={directions}
        initialUsers={userPage.items}
      />
    </AppShell>
  );
}
