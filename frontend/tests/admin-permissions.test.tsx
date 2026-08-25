import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminAnnouncementsPage from "@/app/admin/announcements/page";
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
  getCohortsMock,
  getDirectionsMock,
  requireAdminMock,
} = vi.hoisted(() => ({
  csrfFetchMock: vi.fn(),
  getAdminAnnouncementsMock: vi.fn(),
  getAdminAssignmentsMock: vi.fn(),
  getAdminSessionsMock: vi.fn(),
  getCohortsMock: vi.fn(),
  getDirectionsMock: vi.fn(),
  requireAdminMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  csrfFetch: csrfFetchMock,
}));

vi.mock("@/lib/api/server", () => ({
  getAdminAnnouncements: getAdminAnnouncementsMock,
  getAdminAssignments: getAdminAssignmentsMock,
  getAdminSessions: getAdminSessionsMock,
  getCohorts: getCohortsMock,
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
    requireAdminMock.mockReset();
    requireAdminMock.mockResolvedValue(admin);
    getCohortsMock.mockResolvedValue([]);
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
    expect(screen.getByRole("link", { name: "登录人员" })).toHaveAttribute(
      "href",
      "/admin/sessions",
    );
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
    expect(assignmentLink.className).toContain("rounded-xl");
  });

  it("allows an admin to open the new assignment page", async () => {
    render(await NewAssignmentPage());

    expect(screen.getByRole("heading", { name: "新建作业" })).toBeInTheDocument();
    expect(screen.getByLabelText("标题")).toBeInTheDocument();
    expect(requireAdminMock).toHaveBeenCalledOnce();
  });

  it("renders saved Markdown as a sanitized HTML preview", () => {
    const draft: AssignmentAdmin = {
      ...assignment(),
      description_markdown: "# Electric Control Homework 1\n\n- task1\n- task2",
      description_html:
        "<h2>Electric Control Homework 1</h2><ul><li>task1</li><li>task2</li></ul>",
    };

    render(
      <AssignmentEditor
        cohorts={[]}
        directions={[]}
        initialAssignment={draft}
        initialSubmissions={[]}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Markdown 渲染预览" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Electric Control Homework 1" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByText("# Electric Control Homework 1")).not.toBeInTheDocument();
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
        cohorts={[]}
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
