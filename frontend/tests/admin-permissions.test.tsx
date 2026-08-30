import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminAnnouncementsPage from "@/app/admin/announcements/page";
import AdminCategoriesPage from "@/app/admin/categories/page";
import AdminAssignmentsPage from "@/app/admin/assignments/page";
import AdminSessionsPage from "@/app/admin/sessions/page";
import NewAssignmentPage from "@/app/admin/assignments/new/page";
import { ProfileEditor } from "@/components/admin/profile-editor";
import { AssignmentEditor } from "@/components/admin/assignment-editor";
import { AppShell } from "@/components/layout/app-shell";
import type { AdminSession, AssignmentAdmin, User } from "@/lib/api/types";

const {
  csrfFetchMock,
  getAdminAnnouncementsMock,
  getAdminAssignmentsMock,
  getAdminSessionsMock,
  getDirectionsMock,
  requireAdminMock,
  replaceMock,
} = vi.hoisted(() => ({
  csrfFetchMock: vi.fn(),
  getAdminAnnouncementsMock: vi.fn(),
  getAdminAssignmentsMock: vi.fn(),
  getAdminSessionsMock: vi.fn(),
  getDirectionsMock: vi.fn(),
  requireAdminMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/assignments",
  useRouter: () => ({ refresh: vi.fn(), replace: replaceMock }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  csrfFetch: csrfFetchMock,
}));

vi.mock("@/lib/api/server", () => ({
  getAdminAnnouncements: getAdminAnnouncementsMock,
  getAdminAssignments: getAdminAssignmentsMock,
  getAdminSessions: getAdminSessionsMock,
  getDirections: getDirectionsMock,
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
  email_verified_at: "2026-08-25T00:00:00Z",
  created_at: "2026-08-25T00:00:00Z",
  revision: 3,
};

function assignment(): AssignmentAdmin {
  return {
    id: "assignment-1",
    title: "电控第一次作业",
    description_markdown: "完成电控基础练习。",
    description_html: "<p>完成电控基础练习。</p>",
    training_url: null,
    submission_instructions: "提交 PDF。",
    status: "draft",
    audience: {
      all_students: true,
      cohort_ids: [],
      direction_ids: [],
      match: "intersection",
    },
    allowed_extensions: ["pdf"],
    max_total_bytes: 1024,
    publish_at: "2026-08-25T10:00:00Z",
    published_at: null,
    deadline: "2026-09-01T10:00:00Z",
    closed_at: null,
    archived_at: null,
    estimated_recipient_count: 0,
    actual_recipient_count: 0,
    stats: {
      target_count: 0,
      submitted_count: 0,
      unsubmitted_count: 0,
      feedback_submission_count: 0,
      last_submitted_at: null,
    },
    created_at: "2026-08-25T09:00:00Z",
    updated_at: "2026-08-25T09:00:00Z",
    revision: 3,
  };
}

describe("admin permissions UI", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    csrfFetchMock.mockReset();
    replaceMock.mockReset();
    requireAdminMock.mockReset();
    requireAdminMock.mockResolvedValue(admin);
    getDirectionsMock.mockResolvedValue([]);
    getAdminAnnouncementsMock.mockResolvedValue({ items: [] });
    getAdminAssignmentsMock.mockResolvedValue({ items: [] });
    getAdminSessionsMock.mockResolvedValue([]);
  });

  it("shows assignment management and logged-in people navigation", () => {
    render(<AppShell user={admin}><p>内容</p></AppShell>);

    expect(screen.getByRole("link", { name: "作业管理" })).toHaveAttribute(
      "href",
      "/admin/assignments",
    );
    expect(screen.getByRole("link", { name: "作业管理" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "方向设置" })).toHaveAttribute(
      "href",
      "/admin/categories",
    );
    expect(screen.queryByText("届次与方向")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "登录人员" })).toHaveAttribute(
      "href",
      "/admin/sessions",
    );
  });


  it("uses SVG icons instead of text glyph placeholders", () => {
    render(<AppShell user={admin}><p>内容</p></AppShell>);

    expect(screen.getByRole("link", { name: "作业管理" }).querySelector("svg")).toBeTruthy();
    expect(screen.getByRole("button", { name: "查看学生视图" }).querySelector("svg")).toBeTruthy();
    expect(screen.getByRole("link", { name: "个人资料" }).querySelector("svg")).toBeTruthy();
    expect(screen.getByRole("button", { name: "退出登录" }).querySelector("svg")).toBeTruthy();
  });

  it("switches an administrator into the student view", async () => {
    csrfFetchMock.mockResolvedValue({ ...admin, student_view: true });
    render(<AppShell user={admin}><p>内容</p></AppShell>);

    fireEvent.click(screen.getByRole("button", { name: "查看学生视图" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(csrfFetchMock).toHaveBeenCalledWith("/auth/student-view", {
      method: "POST",
    });
    expect(replaceMock).toHaveBeenCalledWith("/dashboard");
  });

  it("shows student navigation and can return to administrator view", async () => {
    const studentViewAdmin = { ...admin, student_view: true };
    csrfFetchMock.mockResolvedValue({ ...admin, student_view: false });
    render(<AppShell user={studentViewAdmin}><p>内容</p></AppShell>);

    expect(screen.getByRole("link", { name: "工作台" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(screen.queryByRole("link", { name: "管理概览" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "返回管理员视图" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(csrfFetchMock).toHaveBeenCalledWith("/auth/student-view", {
      method: "DELETE",
    });
    expect(replaceMock).toHaveBeenCalledWith("/admin/dashboard");
  });
  it("uses light-blue create links for admin content", async () => {
    const { unmount } = render(await AdminAnnouncementsPage());
    const announcementLink = screen.getByRole("link", { name: "新建通知" });
    expect(announcementLink).toHaveAttribute("href", "/admin/announcements/new");
    expect(announcementLink.className).toContain("bg-[var(--color-action-fill)]");
    expect(screen.getByText("＋")).toBeInTheDocument();

    unmount();
    render(await AdminAssignmentsPage());
    const assignmentLink = screen.getByRole("link", { name: "新建作业" });
    expect(assignmentLink).toHaveAttribute("href", "/admin/assignments/new");
    expect(assignmentLink.className).toContain("rounded-lg");
    expect(assignmentLink.className).toContain("h-9");
  });

  it("keeps the classification page focused on directions", async () => {
    getDirectionsMock.mockResolvedValue([
      {
        id: "direction-1",
        code: "robotics",
        name: "机器人",
        description: null,
        is_active: true,
        revision: 1,
      },
    ]);
    render(await AdminCategoriesPage());

    expect(screen.getByRole("heading", { name: "方向设置" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "新建方向" })).toBeInTheDocument();
    expect(screen.queryByText("新建届次")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("起始年份")).not.toBeInTheDocument();
  });

  it("allows an admin to open the new assignment page", async () => {
    render(await NewAssignmentPage());

    expect(screen.getByRole("heading", { name: "新建作业" })).toBeInTheDocument();
    expect(screen.getByLabelText("标题")).toBeInTheDocument();
    expect(screen.getByText("按技术方向")).toBeInTheDocument();
    expect(screen.queryByText("届次")).not.toBeInTheDocument();
    expect(requireAdminMock).toHaveBeenCalledOnce();
  });

  it("keeps the rendered document above the editable Markdown source", () => {
    const draft: AssignmentAdmin = {
      ...assignment(),
      description_markdown: "# Electric Control Homework 1\n\n- task1\n- task2",
      description_html:
        "<h2>Electric Control Homework 1</h2><ul><li>task1</li><li>task2</li></ul>",
    };

    render(
      <AssignmentEditor
        directions={[]}
        initialAssignment={draft}
        initialSubmissions={[]}
      />,
    );

    const renderedHeading = screen.getByRole("heading", {
      name: "Electric Control Homework 1",
    });
    const source = screen.getByLabelText("Markdown 作业说明");
    expect(renderedHeading).toBeInTheDocument();
    expect(source).toHaveValue(
      "# Electric Control Homework 1\n\n- task1\n- task2",
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(
      renderedHeading.compareDocumentPosition(source) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.queryByText("# Electric Control Homework 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Markdown 渲染预览")).not.toBeInTheDocument();
    expect(screen.queryByText("已清洗 HTML")).not.toBeInTheDocument();
  });

  it("submits changed Markdown through the admin PATCH endpoint", async () => {
    const draft = assignment();
    csrfFetchMock.mockResolvedValue({
      ...draft,
      description_markdown: "# Updated",
      description_html: "<h1>Updated</h1>",
      revision: draft.revision + 1,
    });

    render(
      <AssignmentEditor
        directions={[]}
        initialAssignment={draft}
        initialSubmissions={[]}
      />,
    );
    fireEvent.change(screen.getByLabelText("Markdown 作业说明"), {
      target: { value: "# Updated" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    const [path, request] = csrfFetchMock.mock.calls[0] ?? [];
    expect(path).toBe("/admin/assignments/assignment-1");
    expect(request).toMatchObject({ method: "PATCH" });
    expect(JSON.parse(String(request?.body))).toMatchObject({
      description_markdown: "# Updated",
      revision: draft.revision,
    });
    expect(screen.getByText("作业草稿已保存。")).toBeInTheDocument();
  });

  it("publishes an assignment over HTTP when randomUUID is unavailable", async () => {
    const draft = assignment();
    const published: AssignmentAdmin = {
      ...draft,
      status: "published",
      published_at: "2026-08-25T10:00:00Z",
      revision: 4,
    };
    csrfFetchMock
      .mockResolvedValueOnce(draft)
      .mockResolvedValueOnce(published);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(
      <AssignmentEditor
        directions={[]}
        initialAssignment={draft}
        initialSubmissions={[]}
      />,
    );
    vi.stubGlobal("crypto", {
      randomUUID: undefined,
      getRandomValues: vi.fn((bytes: Uint8Array) => {
        bytes.set(Array.from({ length: 16 }, (_, index) => index));
        return bytes;
      }),
    });
    fireEvent.click(
      screen.getByRole("button", { name: "发布 / 安排发布" }),
    );

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(2));
    expect(csrfFetchMock).toHaveBeenNthCalledWith(
      2,
      "/admin/assignments/assignment-1/publish",
      {
        method: "POST",
        headers: {
          "Idempotency-Key": "00010203-0405-4607-8809-0a0b0c0d0e0f",
        },
      },
    );
    expect(
      screen.getByText("作业已发布并固化受众快照。"),
    ).toBeInTheDocument();
  });

  it("keeps the assignment when delete confirmation is cancelled", () => {
    const published: AssignmentAdmin = {
      ...assignment(),
      status: "published",
      published_at: "2026-08-25T10:00:00Z",
    };
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(
      <AssignmentEditor
        directions={[]}
        initialAssignment={published}
        initialSubmissions={[]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "删除作业" }));

    expect(confirm).toHaveBeenCalledOnce();
    expect(csrfFetchMock).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("confirms and deletes a published assignment before returning to the list", async () => {
    const published: AssignmentAdmin = {
      ...assignment(),
      status: "published",
      published_at: "2026-08-25T10:00:00Z",
    };
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue(undefined);

    render(
      <AssignmentEditor
        directions={[]}
        initialAssignment={published}
        initialSubmissions={[]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "删除作业" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining("学生列表、详情和优秀作业入口隐藏"),
    );
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/assignments/assignment-1",
      { method: "DELETE" },
    );
    expect(replaceMock).toHaveBeenCalledWith("/admin/assignments");
  });

  it("saves the admin own profile through the audited admin endpoint", async () => {
    csrfFetchMock.mockResolvedValue({ ...admin, full_name: "新管理员", revision: 4 });
    render(<ProfileEditor initialUser={admin} />);

    fireEvent.change(screen.getByLabelText("真实姓名"), {
      target: { value: "新管理员" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存个人资料" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/users/admin-id",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(JSON.parse(String(csrfFetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      revision: 3,
      full_name: "新管理员",
    });
  });

  it("renders active logged-in people for administrators", async () => {
    const session: AdminSession = {
      id: "session-id",
      user_id: admin.id,
      user_full_name: admin.full_name,
      user_email: admin.email,
      user_role: "admin",
      user_status: "active",
      created_at: "2026-08-25T00:00:00Z",
      last_seen_at: "2026-08-25T01:00:00Z",
      idle_expires_at: "2026-08-25T05:00:00Z",
      absolute_expires_at: "2026-09-01T00:00:00Z",
      ip_prefix: "192.0.2.0/24",
      user_agent_summary: "Browser / Linux",
      is_current: true,
    };
    getAdminSessionsMock.mockResolvedValue([session]);

    render(await AdminSessionsPage());

    expect(screen.getByRole("heading", { name: "登录人员" })).toBeInTheDocument();
    expect(
      screen.getByText((_, element) =>
        element?.tagName === "P" && element.textContent?.includes(admin.email) === true,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("当前设备")).toBeInTheDocument();
  });
});
