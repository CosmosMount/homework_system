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
  redirectMock,
  refreshMock,
  replaceMock,
  getAdminAnnouncementsMock,
  getAdminAssignmentsMock,
  getAdminUsersMock,
  getAuditLogsMock,
  getDirectionsMock,
  getOutboxJobsMock,
  requireAdminMock,
} = vi.hoisted(() => ({
  csrfFetchMock: vi.fn(),
  redirectMock: vi.fn(),
  refreshMock: vi.fn(),
  replaceMock: vi.fn(),
  getAdminAnnouncementsMock: vi.fn(),
  getAdminAssignmentsMock: vi.fn(),
  getAdminUsersMock: vi.fn(),
  getAuditLogsMock: vi.fn(),
  getDirectionsMock: vi.fn(),
  getOutboxJobsMock: vi.fn(),
  requireAdminMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
  usePathname: () => "/admin/users",
  useRouter: () => ({ refresh: refreshMock, replace: replaceMock }),
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

function userPage(
  items: AdminUser[],
  total = items.length,
  page = 1,
  pageSize = 20,
): AdminUserPage {
  return {
    items,
    page,
    page_size: pageSize,
    total,
  };
}

describe("admin account activity UI", () => {
  beforeEach(() => {
    csrfFetchMock.mockReset();
    redirectMock.mockReset();
    refreshMock.mockReset();
    replaceMock.mockReset();
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
      (query?: {
        activity?: "inactive";
        page?: number;
        pageSize?: number;
        search?: string;
      }) =>
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

  it("passes the activity, page and search filters to the admin user API", async () => {
    getAdminUsersMock.mockResolvedValueOnce(userPage([inactiveUser], 155, 2, 20));
    render(
      await AdminUsersPage({
        searchParams: Promise.resolve({
          activity: "inactive",
          page: "2",
          search: "沉睡学生",
        }),
      }),
    );

    expect(getAdminUsersMock).toHaveBeenCalledWith({
      activity: "inactive",
      page: 2,
      pageSize: 20,
      search: "沉睡学生",
    });
    expect(
      screen.getByRole("link", { name: "超过 10 天未进入" }),
    ).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "沉睡学生" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "近期学生" })).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "搜索用户" })).toHaveValue(
      "沉睡学生",
    );

    getAdminUsersMock.mockResolvedValueOnce(userPage([], 155, 999, 20));
    await AdminUsersPage({
      searchParams: Promise.resolve({
        activity: "inactive",
        page: "999",
        search: "沉睡学生",
      }),
    });

    expect(redirectMock).toHaveBeenCalledOnce();
    const redirectUrl = new URL(
      String(redirectMock.mock.calls[0]?.[0]),
      "https://example.test",
    );
    expect(redirectUrl.searchParams.get("activity")).toBe("inactive");
    expect(redirectUrl.searchParams.get("search")).toBe("沉睡学生");
    expect(redirectUrl.searchParams.get("page")).toBe("8");
  });

  it("exposes every server page instead of treating the first 100 users as complete", () => {
    render(
      <UserAdminPanel
        activity="inactive"
        directions={directions}
        initialTotal={155}
        initialUsers={[inactiveUser]}
        page={2}
        pageSize={20}
        search="待处理账号"
      />,
    );

    expect(screen.getByText("本页显示 1 个，共 155 个匹配账号")).toBeInTheDocument();
    expect(screen.getByText("第 2 / 8 页")).toBeInTheDocument();

    const previous = screen.getByRole("link", { name: "上一页" });
    const next = screen.getByRole("link", { name: "下一页" });
    const previousUrl = new URL(previous.getAttribute("href") ?? "", "https://example.test");
    const nextUrl = new URL(next.getAttribute("href") ?? "", "https://example.test");
    expect(previousUrl.searchParams.get("page")).toBeNull();
    expect(nextUrl.searchParams.get("page")).toBe("3");
    for (const url of [previousUrl, nextUrl]) {
      expect(url.searchParams.get("search")).toBe("待处理账号");
      expect(url.searchParams.get("activity")).toBe("inactive");
    }
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
    ).toHaveLength(3);
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
        search="学生"
      />,
    );

    fireEvent.change(screen.getByLabelText("操作原因"), {
      target: { value: "协助平台管理" },
    });
    fireEvent.click(screen.getByRole("button", { name: "设为管理员" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(refreshMock).toHaveBeenCalledOnce();
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

  it("submits all inline confirmations and removes a deleted account", async () => {
    csrfFetchMock.mockResolvedValue(undefined);
    const { unmount } = render(
      <UserAdminPanel
        activity="inactive"
        directions={directions}
        initialTotal={1}
        initialUsers={[inactiveUser]}
      />,
    );
    fireEvent.change(screen.getByLabelText("永久删除原因"), {
      target: { value: "用户提出删除请求" },
    });
    fireEvent.change(screen.getByLabelText("管理员当前密码"), {
      target: { value: "admin-current-password" },
    });
    fireEvent.change(screen.getByLabelText("确认目标账号邮箱"), {
      target: { value: inactiveUser.email },
    });
    fireEvent.click(
      screen.getByLabelText(/我已确认近期 PostgreSQL 与 MinIO 加密备份可恢复/),
    );

    fireEvent.click(screen.getByRole("button", { name: "永久删除账号" }));
    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(refreshMock).toHaveBeenCalledOnce();
    expect(replaceMock).not.toHaveBeenCalled();
    expect(csrfFetchMock).toHaveBeenCalledWith("/admin/users/inactive-id", {
      method: "DELETE",
      body: JSON.stringify({
        reason: "用户提出删除请求",
        current_password: "admin-current-password",
        confirmation_email: inactiveUser.email,
        backup_confirmed: true,
      }),
    });
    expect(
      screen.queryByRole("heading", { name: "沉睡学生" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("本页显示 0 个，共 0 个匹配账号")).toBeInTheDocument();
    expect(screen.getByText("已永久删除账号 沉睡学生。")).toBeInTheDocument();
    unmount();
    csrfFetchMock.mockClear();
    refreshMock.mockClear();
    replaceMock.mockClear();

    render(
      <UserAdminPanel
        activity="inactive"
        directions={directions}
        initialTotal={141}
        initialUsers={[inactiveUser]}
        page={8}
        pageSize={20}
        search="沉睡"
      />,
    );
    fireEvent.change(screen.getByLabelText("永久删除原因"), {
      target: { value: "用户提出删除请求" },
    });
    fireEvent.change(screen.getByLabelText("管理员当前密码"), {
      target: { value: "admin-current-password" },
    });
    fireEvent.change(screen.getByLabelText("确认目标账号邮箱"), {
      target: { value: inactiveUser.email },
    });
    fireEvent.click(
      screen.getByLabelText(/我已确认近期 PostgreSQL 与 MinIO 加密备份可恢复/),
    );

    fireEvent.click(screen.getByRole("button", { name: "永久删除账号" }));
    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(refreshMock).not.toHaveBeenCalled();
    expect(replaceMock).toHaveBeenCalledOnce();
    const replacementUrl = new URL(
      String(replaceMock.mock.calls[0]?.[0]),
      "https://example.test",
    );
    expect(replacementUrl.searchParams.get("activity")).toBe("inactive");
    expect(replacementUrl.searchParams.get("search")).toBe("沉睡");
    expect(replacementUrl.searchParams.get("page")).toBe("7");
  });

  it("shows deletion for a recent account and rejects a mismatched email locally", () => {
    render(
      <UserAdminPanel
        activity={null}
        directions={directions}
        initialTotal={1}
        initialUsers={[recentUser]}
      />,
    );
    fireEvent.change(screen.getByLabelText("永久删除原因"), {
      target: { value: "用户提出删除请求" },
    });
    fireEvent.change(screen.getByLabelText("管理员当前密码"), {
      target: { value: "admin-current-password" },
    });
    fireEvent.change(screen.getByLabelText("确认目标账号邮箱"), {
      target: { value: inactiveUser.email },
    });
    fireEvent.click(
      screen.getByLabelText(/我已确认近期 PostgreSQL 与 MinIO 加密备份可恢复/),
    );
    fireEvent.click(screen.getByRole("button", { name: "永久删除账号" }));

    expect(
      screen.getByText("确认邮箱必须与待删除账号邮箱完全一致。"),
    ).toBeInTheDocument();
    expect(csrfFetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "近期学生" })).toBeInTheDocument();
  });

  it("keeps the account, displays backend denial and clears the password field", async () => {
    csrfFetchMock.mockRejectedValue(
      new ApiError(new Response(null, { status: 401 }), {
        error: {
          code: "INVALID_CREDENTIALS",
          message: "当前密码不正确。",
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
    fireEvent.change(screen.getByLabelText("永久删除原因"), {
      target: { value: "用户提出删除请求" },
    });
    const password = screen.getByLabelText("管理员当前密码");
    fireEvent.change(password, {
      target: { value: "wrong-password" },
    });
    fireEvent.change(screen.getByLabelText("确认目标账号邮箱"), {
      target: { value: inactiveUser.email },
    });
    fireEvent.click(
      screen.getByLabelText(/我已确认近期 PostgreSQL 与 MinIO 加密备份可恢复/),
    );
    fireEvent.click(screen.getByRole("button", { name: "永久删除账号" }));

    expect(await screen.findByText("当前密码不正确。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "沉睡学生" })).toBeInTheDocument();
    expect(password).toHaveValue("");
  });
});
