import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminAnnouncementsPage from "@/app/admin/announcements/page";
import AdminCategoriesPage from "@/app/admin/categories/page";
import AdminAssignmentsPage from "@/app/admin/assignments/page";
import AdminSubmissionPage from "@/app/admin/submissions/[submissionId]/page";
import AdminSessionsPage from "@/app/admin/sessions/page";
import NewAssignmentPage from "@/app/admin/assignments/new/page";
import { ProfileEditor } from "@/components/admin/profile-editor";
import { AssignmentEditor } from "@/components/admin/assignment-editor";
import { AppShell } from "@/components/layout/app-shell";
import { ApiError } from "@/lib/api/client";
import type { AdminSession, AssignmentAdmin, User } from "@/lib/api/types";

const {
  apiFetchMock,
  csrfFetchMock,
  getAdminAnnouncementMock,
  getAdminAnnouncementsMock,
  getAdminAssignmentMock,
  getAdminAssignmentsMock,
  getAdminSessionsMock,
  getDirectionsMock,
  getExcellentSubmissionsMock,
  getSubmissionMock,
  requireAdminMock,
  replaceMock,
} = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  csrfFetchMock: vi.fn(),
  getAdminAnnouncementMock: vi.fn(),
  getAdminAnnouncementsMock: vi.fn(),
  getAdminAssignmentMock: vi.fn(),
  getAdminAssignmentsMock: vi.fn(),
  getAdminSessionsMock: vi.fn(),
  getDirectionsMock: vi.fn(),
  getExcellentSubmissionsMock: vi.fn(),
  getSubmissionMock: vi.fn(),
  requireAdminMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  usePathname: () => "/admin/assignments",
  useRouter: () => ({ refresh: vi.fn(), replace: replaceMock }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiFetch: apiFetchMock,
  csrfFetch: csrfFetchMock,
}));

vi.mock("@/lib/api/server", () => ({
  getAdminAnnouncement: getAdminAnnouncementMock,
  getAdminAnnouncements: getAdminAnnouncementsMock,
  getAdminAssignment: getAdminAssignmentMock,
  getAdminAssignments: getAdminAssignmentsMock,
  getAdminSessions: getAdminSessionsMock,
  getDirections: getDirectionsMock,
  getExcellentSubmissions: getExcellentSubmissionsMock,
  getSubmission: getSubmissionMock,
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
      completed_count: 0,
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
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue({ count: 0 });
    csrfFetchMock.mockReset();
    replaceMock.mockReset();
    requireAdminMock.mockReset();
    requireAdminMock.mockResolvedValue(admin);
    getDirectionsMock.mockResolvedValue([]);
    getAdminAnnouncementsMock.mockResolvedValue({ items: [] });
    getAdminAssignmentMock.mockResolvedValue(assignment());
    getAdminAssignmentsMock.mockResolvedValue({ items: [] });
    getAdminSessionsMock.mockResolvedValue([]);
    getExcellentSubmissionsMock.mockResolvedValue([]);
    getSubmissionMock.mockResolvedValue({
      id: "submission-1",
      assignment_id: "assignment-1",
      owner_user_id: "student-1",
      latest_version_id: "version-1",
      versions: [
        {
          id: "version-1",
          submission_id: "submission-1",
          version_number: 1,
          submitted_by: "student-1",
          text_html: "<p>提交正文</p>",
          external_url: null,
          total_file_bytes: 0,
          submitted_at: "2026-08-25T10:00:00Z",
          attachments: [],
          feedback: null,
        },
      ],
    });
  });

  it("returns from a personal submission to its original assignment", async () => {
    render(
      await AdminSubmissionPage({
        params: Promise.resolve({ submissionId: "submission-1" }),
      }),
    );

    expect(screen.getByRole("link", { name: "返回原作业" })).toHaveAttribute(
      "href",
      "/admin/assignments/assignment-1/edit",
    );
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

  it("edits a published assignment audience while preserving frozen file rules", async () => {
    const published: AssignmentAdmin = {
      ...assignment(),
      status: "published",
      published_at: "2026-08-25T10:00:39.321Z",
      publish_at: "2026-08-25T10:00:37.321Z",
      deadline: "2026-09-01T10:00:42.111Z",
      stats: {
        ...assignment().stats,
        submitted_count: 1,
        last_submitted_at: "2026-08-30T09:30:15Z",
      },
    };
    const updated = {
      ...published,
      title: "修正后的已发布作业",
      audience: {
        all_students: false,
        cohort_ids: [],
        direction_ids: ["direction-1"],
        match: "intersection" as const,
      },
      deadline: new Date("2026-08-31T18:00").toISOString(),
      revision: published.revision + 1,
    };
    csrfFetchMock.mockResolvedValue(updated);

    render(
      <AssignmentEditor
        directions={[
          {
            id: "direction-1",
            code: "ec",
            name: "电控",
            description: null,
            is_active: true,
            revision: 1,
          },
        ]}
        initialAssignment={published}
        initialSubmissions={[]}
      />,
    );

    expect(screen.getByLabelText("标题")).toBeEnabled();
    expect(screen.getByLabelText("Markdown 作业说明")).toBeEnabled();
    expect(screen.getByLabelText("公共截止")).toBeEnabled();
    expect(screen.getByLabelText("全部激活学生")).toBeEnabled();
    expect(screen.getByLabelText("允许扩展名（逗号分隔）")).toBeDisabled();
    expect(screen.getByLabelText("单版本附件总上限（字节）")).toBeDisabled();
    expect(screen.getByLabelText("发布时间")).toBeDisabled();
    expect(screen.getByText(/最后正式提交/)).toHaveTextContent("2026年8月30日 17:30");

    fireEvent.change(screen.getByLabelText("标题"), {
      target: { value: "修正后的已发布作业" },
    });
    fireEvent.change(screen.getByLabelText("公共截止"), {
      target: { value: "2026-08-31T18:00" },
    });
    fireEvent.click(screen.getByLabelText("按技术方向"));
    fireEvent.click(screen.getByLabelText("电控"));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    const [path, request] = csrfFetchMock.mock.calls[0] ?? [];
    expect(path).toBe("/admin/assignments/assignment-1");
    expect(request).toMatchObject({ method: "PATCH" });
    expect(JSON.parse(String(request?.body))).toMatchObject({
      revision: published.revision,
      title: "修正后的已发布作业",
      audience: {
        all_students: false,
        cohort_ids: [],
        direction_ids: ["direction-1"],
        match: "intersection",
      },
      allowed_extensions: published.allowed_extensions,
      max_total_bytes: published.max_total_bytes,
      publish_at: "2026-08-25T10:00:37.321Z",
      deadline: new Date("2026-08-31T18:00").toISOString(),
    });
    expect(screen.getByText("作业已更新。")).toBeInTheDocument();
  });

  it("separates submitted, unsubmitted and historical submitters", () => {
    const published: AssignmentAdmin = {
      ...assignment(),
      status: "published",
      published_at: "2026-08-25T10:00:00Z",
    };
    render(
      <AssignmentEditor
        directions={[]}
        initialAssignment={published}
        initialSubmissions={[
          {
            user_id: "submitted-user",
            full_name: "已提交同学",
            student_number: "1001",
            cohort_id: null,
            direction_id: null,
            submission_id: "submission-1",
            latest_version_number: 2,
            last_submitted_at: "2026-08-26T10:00:00Z",
            completed_version_id: null,
            completed_at: null,
            is_completed: false,
            has_feedback: true,
            in_current_audience: true,
          },
          {
            user_id: "unsubmitted-user",
            full_name: "未提交同学",
            student_number: "1002",
            cohort_id: null,
            direction_id: null,
            submission_id: null,
            latest_version_number: null,
            last_submitted_at: null,
            completed_version_id: null,
            completed_at: null,
            is_completed: false,
            has_feedback: false,
            in_current_audience: true,
          },
          {
            user_id: "historical-user",
            full_name: "历史提交同学",
            student_number: "1003",
            cohort_id: null,
            direction_id: null,
            submission_id: "submission-3",
            latest_version_number: 1,
            last_submitted_at: "2026-08-25T10:00:00Z",
            completed_version_id: null,
            completed_at: null,
            is_completed: false,
            has_feedback: false,
            in_current_audience: false,
          },
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: /已提交.*\(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /未提交.*\(1\)/ })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /历史提交（已不在当前受众）.*\(1\)/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("已提交同学")).toBeInTheDocument();
    expect(screen.getByText("未提交同学")).toBeInTheDocument();
    expect(screen.getByText("历史提交同学")).toBeInTheDocument();
    expect(screen.getAllByText("管理个人延期")).toHaveLength(2);
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

  it("restores a stale admin student-view session before publishing", async () => {
    const draft = assignment();
    const published: AssignmentAdmin = {
      ...draft,
      status: "published",
      published_at: "2026-08-25T10:00:00Z",
      revision: 4,
    };
    const forbidden = new ApiError(
      new Response(null, { status: 403 }),
      {
        error: {
          code: "FORBIDDEN",
          message: "权限不足。",
          request_id: "request-id",
        },
      },
    );
    csrfFetchMock
      .mockRejectedValueOnce(forbidden)
      .mockResolvedValueOnce({ ...admin, student_view: false })
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
    fireEvent.click(
      screen.getByRole("button", { name: "发布 / 安排发布" }),
    );

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(4));
    expect(csrfFetchMock).toHaveBeenNthCalledWith(
      1,
      "/admin/assignments/assignment-1",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(csrfFetchMock).toHaveBeenNthCalledWith(2, "/auth/student-view", {
      method: "DELETE",
    });
    expect(csrfFetchMock).toHaveBeenNthCalledWith(
      3,
      "/admin/assignments/assignment-1",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(csrfFetchMock).toHaveBeenNthCalledWith(
      4,
      "/admin/assignments/assignment-1/publish",
      expect.objectContaining({ method: "POST" }),
    );
    expect(
      screen.getByText("作业已发布并固化受众快照。"),
    ).toBeInTheDocument();
  });

  it("does not retry when the session cannot restore administrator view", async () => {
    const forbidden = new ApiError(
      new Response(null, { status: 403 }),
      {
        error: {
          code: "FORBIDDEN",
          message: "权限不足。",
          request_id: "request-id",
        },
      },
    );
    csrfFetchMock.mockRejectedValue(forbidden);

    render(
      <AssignmentEditor
        directions={[]}
        initialAssignment={assignment()}
        initialSubmissions={[]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(screen.getByText("权限不足。")).toBeInTheDocument();
    });
    expect(csrfFetchMock).toHaveBeenCalledTimes(2);
    expect(csrfFetchMock).toHaveBeenNthCalledWith(2, "/auth/student-view", {
      method: "DELETE",
    });
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
      remembered: true,
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
    expect(screen.getByText("已记住登录")).toBeInTheDocument();
  });
});
