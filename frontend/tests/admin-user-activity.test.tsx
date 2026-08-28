import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminDashboardPage from "@/app/admin/dashboard/page";
import AdminUsersPage from "@/app/admin/users/page";
import { UserAdminPanel } from "@/components/admin/user-admin-panel";
import { ApiError } from "@/lib/api/client";
import type {
  AdminUser,
  AdminUserPage,
  Direction,
  User,
} from "@/lib/api/types";

const {
  csrfFetchMock,
  getAdminAnnouncementsMock,
  getAdminAssignmentsMock,
  getAdminUsersMock,
  getAuditLogsMock,
  getDirectionsMock,
  getOutboxJobsMock,
  requireAdminMock,
} = vi.hoisted(() => ({
  csrfFetchMock: vi.fn(),
  getAdminAnnouncementsMock: vi.fn(),
  getAdminAssignmentsMock: vi.fn(),
  getAdminUsersMock: vi.fn(),
  getAuditLogsMock: vi.fn(),
  getDirectionsMock: vi.fn(),
  getOutboxJobsMock: vi.fn(),
  requireAdminMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/users",
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  csrfFetch: csrfFetchMock,
}));

vi.mock("@/lib/api/server", () => ({
  getAdminAnnouncements: getAdminAnnouncementsMock,
  getAdminAssignments: getAdminAssignmentsMock,
  getAdminUsers: getAdminUsersMock,
  getAuditLogs: getAuditLogsMock,
  getDirections: getDirectionsMock,
  getOutboxJobs: getOutboxJobsMock,
  requireAdmin: requireAdminMock,
}));

const admin: User = {
  id: "admin-id",
  email: "admin@connect.hkust-gz.edu.cn",
  student_number: "A001",
  full_name: "管理员",
  role: "admin",
  status: "active",
  cohort: null,
  direction: null,
  email_verified_at: "2026-08-01T00:00:00Z",
  created_at: "2026-08-01T00:00:00Z",
  revision: 1,
};

const inactiveUser: AdminUser = {
  id: "inactive-id",
  email: "inactive@connect.hkust-gz.edu.cn",
  student_number: "S001",
  full_name: "沉睡学生",
  role: "student",
  status: "active",
  cohort: null,
  direction: null,
  email_verified_at: "2026-08-01T00:00:00Z",
  created_at: "2026-08-01T00:00:00Z",
  revision: 2,
  last_active_at: "2026-08-10T01:30:00Z",
  is_inactive: true,
  inactive_days: 16,
};

const recentUser: AdminUser = {
  ...inactiveUser,
  id: "recent-id",
  email: "recent@connect.hkust-gz.edu.cn",
  student_number: "S002",
  full_name: "近期学生",
  last_active_at: "2026-08-26T02:00:00Z",
  is_inactive: false,
  inactive_days: 1,
};

const neverEnteredUser: AdminUser = {
  ...inactiveUser,
  id: "never-id",
  email: "never@connect.hkust-gz.edu.cn",
  student_number: "S003",
  full_name: "新注册学生",
  email_verified_at: "2026-08-25T00:00:00Z",
  created_at: "2026-08-25T00:00:00Z",
  last_active_at: null,
  is_inactive: false,
  inactive_days: 2,
};

const pendingUser: AdminUser = {
  ...neverEnteredUser,
  id: "pending-id",
  email: "pending@connect.hkust-gz.edu.cn",
  student_number: "S004",
  full_name: "待验证学生",
  status: "pending_email",
};

const disabledUser: AdminUser = {
  ...recentUser,
  id: "disabled-id",
  email: "disabled@connect.hkust-gz.edu.cn",
  student_number: "S005",
  full_name: "停用学生",
  status: "disabled",
};

const directions: Direction[] = [];

function userPage(items: AdminUser[], total = items.length): AdminUserPage {
  return {
    items,
    page: 1,
    page_size: 100,
    total,
  };
}

describe("admin account activity UI", () => {
  beforeEach(() => {
    csrfFetchMock.mockReset();
    getAdminAnnouncementsMock.mockReset();
    getAdminAssignmentsMock.mockReset();
    getAdminUsersMock.mockReset();
    getAuditLogsMock.mockReset();
    getDirectionsMock.mockReset();
    getOutboxJobsMock.mockReset();
    requireAdminMock.mockReset();

    requireAdminMock.mockResolvedValue(admin);
    getAdminAnnouncementsMock.mockResolvedValue({ items: [], total: 0 });
    getAdminAssignmentsMock.mockResolvedValue({ items: [], total: 0 });
    getAuditLogsMock.mockResolvedValue({ items: [] });
    getDirectionsMock.mockResolvedValue(directions);
    getOutboxJobsMock.mockResolvedValue({ items: [] });
    getAdminUsersMock.mockImplementation(
      (query?: { activity?: "inactive" }) =>
        Promise.resolve(
          query?.activity === "inactive"
            ? userPage([inactiveUser], 1)
            : userPage([inactiveUser, recentUser, neverEnteredUser], 3),
        ),
    );
  });

  it("shows an accurate dashboard reminder linked to the inactive filter", async () => {
    render(await AdminDashboardPage());

    const reminder = screen.getByRole("link", {
      name: /超过 10 天未进入/,
    });
    expect(reminder).toHaveAttribute(
      "href",
      "/admin/users?activity=inactive",
    );
    expect(within(reminder).getByText("1")).toBeInTheDocument();
    expect(getAdminUsersMock).toHaveBeenCalledWith({
      activity: "inactive",
      pageSize: 1,
    });
  });

  it("passes only the supported activity filter to the admin user API", async () => {
    render(
      await AdminUsersPage({
        searchParams: Promise.resolve({ activity: "inactive" }),
      }),
    );

    expect(getAdminUsersMock).toHaveBeenCalledWith({
      activity: "inactive",
      pageSize: 100,
    });
    expect(
      screen.getByRole("link", { name: "超过 10 天未进入" }),
    ).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "沉睡学生" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "近期学生" })).not.toBeInTheDocument();
  });

  it("renders recent, inactive and never-entered activity states", () => {
    const { container } = render(
      <UserAdminPanel
        activity={null}
        directions={directions}
        initialTotal={3}
        initialUsers={[inactiveUser, recentUser, neverEnteredUser]}
      />,
    );

    expect(screen.getByText("16 天未登录")).toBeInTheDocument();
    expect(screen.getByText("从未进入系统")).toBeInTheDocument();
    expect(
      container.querySelector(
        'time[datetime="2026-08-26T02:00:00Z"]',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "永久删除账号" }),
    ).toHaveLength(1);
  });

  it("keeps activity fields after an ordinary profile update", async () => {
    csrfFetchMock.mockResolvedValue({
      ...inactiveUser,
      full_name: "更新后学生",
      revision: 3,
    });
    const { container } = render(
      <UserAdminPanel
        activity={null}
        directions={directions}
        initialTotal={1}
        initialUsers={[inactiveUser]}
      />,
    );

    fireEvent.change(screen.getByLabelText("姓名"), {
      target: { value: "更新后学生" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存资料" }));

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "更新后学生" }),
      ).toBeInTheDocument(),
    );
    expect(
      container.querySelector(
        'time[datetime="2026-08-10T01:30:00Z"]',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("16 天未登录")).toBeInTheDocument();
  });

  it("uses localized semantic badges for every account status", () => {
    render(
      <UserAdminPanel
        activity={null}
        directions={directions}
        initialTotal={3}
        initialUsers={[recentUser, pendingUser, disabledUser]}
      />,
    );

    expect(screen.getByLabelText("账号状态：正常")).toHaveClass(
      "rounded-full",
      "bg-emerald-50",
    );
    expect(screen.getByLabelText("账号状态：待验证")).toHaveClass(
      "rounded-full",
      "bg-amber-50",
    );
    expect(screen.getByLabelText("账号状态：已禁用")).toHaveClass(
      "rounded-full",
      "bg-rose-50",
    );
    expect(screen.queryByText("active")).not.toBeInTheDocument();
    expect(screen.queryByText("pending_email")).not.toBeInTheDocument();
    expect(screen.queryByText("disabled")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("搜索用户"), {
      target: { value: "已禁用" },
    });
    expect(screen.getByRole("heading", { name: "停用学生" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "近期学生" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "待验证学生" })).not.toBeInTheDocument();
  });

  it("dispatches the clicked role action and updates the account role", async () => {
    csrfFetchMock.mockResolvedValue({
      ...recentUser,
      role: "admin",
      revision: 3,
    });
    render(
      <UserAdminPanel
        activity={null}
        directions={directions}
        initialTotal={1}
        initialUsers={[recentUser]}
      />,
    );

    fireEvent.change(screen.getByLabelText("操作原因"), {
      target: { value: "协助平台管理" },
    });
    fireEvent.click(screen.getByRole("button", { name: "设为管理员" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(csrfFetchMock).toHaveBeenCalledWith("/admin/users/recent-id/role", {
      method: "POST",
      body: JSON.stringify({
        role: "admin",
        reason: "协助平台管理",
      }),
    });
    expect(
      screen.getByRole("button", { name: "改为学生" }),
    ).toBeInTheDocument();
  });

  it("requires confirmation and removes a successfully deleted account", async () => {
    const confirm = vi
      .spyOn(window, "confirm")
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    csrfFetchMock.mockResolvedValue(undefined);
    render(
      <UserAdminPanel
        activity="inactive"
        directions={directions}
        initialTotal={1}
        initialUsers={[inactiveUser]}
      />,
    );
    fireEvent.change(screen.getByLabelText("操作原因"), {
      target: { value: "长期未使用" },
    });

    fireEvent.click(screen.getByRole("button", { name: "永久删除账号" }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(csrfFetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "永久删除账号" }));
    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(csrfFetchMock).toHaveBeenCalledWith("/admin/users/inactive-id", {
      method: "DELETE",
      body: JSON.stringify({ reason: "长期未使用" }),
    });
    expect(
      screen.queryByRole("heading", { name: "沉睡学生" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("显示 0 / 0 个账号")).toBeInTheDocument();
    expect(screen.getByText("已永久删除账号 沉睡学生。")).toBeInTheDocument();
  });

  it("keeps the account and displays a backend deletion conflict", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockRejectedValue(
      new ApiError(new Response(null, { status: 409 }), {
        error: {
          code: "ACCOUNT_HAS_RETAINED_DATA",
          message: "账号存在需保留业务数据，请改为禁用账号。",
          request_id: "request-id",
        },
      }),
    );
    render(
      <UserAdminPanel
        activity="inactive"
        directions={directions}
        initialTotal={1}
        initialUsers={[inactiveUser]}
      />,
    );
    fireEvent.change(screen.getByLabelText("操作原因"), {
      target: { value: "长期未使用" },
    });
    fireEvent.click(screen.getByRole("button", { name: "永久删除账号" }));

    expect(
      await screen.findByText("账号存在需保留业务数据，请改为禁用账号。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "沉睡学生" })).toBeInTheDocument();
  });
});
