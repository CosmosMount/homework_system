import { redirect } from "next/navigation";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { UserAdminPanel } from "@/components/admin/user-admin-panel";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminUsers,
  getDirections,
  requireAdmin,
} from "@/lib/api/server";

type AdminUsersPageProps = Readonly<{
  searchParams: Promise<{
    activity?: string | string[];
    page?: string | string[];
    search?: string | string[];
  }>;
}>;

const USER_PAGE_SIZE = 20;
const MAX_USER_PAGE = 10_000;

function singleValue(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function parsePage(value: string | undefined): number {
  if (value === undefined || !/^\d+$/.test(value)) return 1;
  const page = Number(value);
  return Number.isSafeInteger(page) && page >= 1 ? Math.min(page, MAX_USER_PAGE) : 1;
}

function adminUsersHref({
  activity,
  page,
  search,
}: Readonly<{
  activity: "inactive" | null;
  page: number;
  search: string;
}>): string {
  const params = new URLSearchParams();
  if (activity === "inactive") params.set("activity", activity);
  if (search) params.set("search", search);
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return "/admin/users" + (query ? "?" + query : "");
}

export default async function AdminUsersPage({
  searchParams,
}: AdminUsersPageProps) {
  const [admin, directions, filters] = await Promise.all([
    requireAdmin(),
    getDirections(),
    searchParams,
  ]);
  const activityValue = singleValue(filters.activity);
  const activity = activityValue === "inactive" ? "inactive" : null;
  const page = parsePage(singleValue(filters.page));
  const search = singleValue(filters.search)?.trim().slice(0, 200) ?? "";
  const userPage = await getAdminUsers({
    activity: activity ?? undefined,
    page,
    pageSize: USER_PAGE_SIZE,
    search: search || undefined,
  });
  const totalPages = Math.max(1, Math.ceil(userPage.total / userPage.page_size));
  if (page > totalPages) {
    redirect(
      adminUsersHref({
        activity,
        page: totalPages,
        search,
      }),
    );
  }
  const resultKey = `${activity ?? "all"}:${search}:${userPage.page}:${userPage.total}:${userPage.items.map((user) => `${user.id}:${user.revision}`).join(",")}`;
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / USERS"
        title="用户管理"
        description="管理账号、技术方向与最近进入时间；超过 10 天未进入的账号可在后端复核后安全清理。"
      />
      <UserAdminPanel
        activity={activity}
        key={resultKey}
        directions={directions}
        initialTotal={userPage.total}
        initialUsers={userPage.items}
        page={userPage.page}
        pageSize={userPage.page_size}
        search={search}
      />
    </AppShell>
  );
}
