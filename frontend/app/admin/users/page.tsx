import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { UserAdminPanel } from "@/components/admin/user-admin-panel";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminUsers,
  getDirections,
  requireAdmin,
} from "@/lib/api/server";

type AdminUsersPageProps = Readonly<{
  searchParams: Promise<{ activity?: string }>;
}>;

export default async function AdminUsersPage({
  searchParams,
}: AdminUsersPageProps) {
  const [admin, directions, filters] = await Promise.all([
    requireAdmin(),
    getDirections(),
    searchParams,
  ]);
  const activity = filters.activity === "inactive" ? "inactive" : null;
  const userPage = await getAdminUsers({
    activity: activity ?? undefined,
    pageSize: 100,
  });
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / USERS"
        title="用户管理"
        description="管理账号、技术方向与最近进入时间；超过 10 天未进入的账号可在后端复核后安全清理。"
      />
      <UserAdminPanel
        activity={activity}
        directions={directions}
        initialTotal={userPage.total}
        initialUsers={userPage.items}
      />
    </AppShell>
  );
}
