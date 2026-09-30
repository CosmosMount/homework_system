import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AssignmentsPage from "@/app/assignments/page";
import AssignmentDetailPage from "@/app/assignments/[assignmentId]/page";
import DashboardPage from "@/app/dashboard/page";
import ExcellentSubmissionPage from "@/app/assignments/[assignmentId]/excellent-submissions/[versionId]/page";
import type {
  AssignmentPage,
  Dashboard,
  ExcellentSubmissionDetail,
  User,
} from "@/lib/api/types";

const {
  getAssignmentsMock,
  getDashboardMock,
  getExcellentSubmissionMock,
  getAssignmentMock,
  getAssignmentSubmissionMock,
  requireUserMock,
} = vi.hoisted(() => ({
  getAssignmentsMock: vi.fn(),
  getDashboardMock: vi.fn(),
  getExcellentSubmissionMock: vi.fn(),
  getAssignmentMock: vi.fn(),
  getAssignmentSubmissionMock: vi.fn(),
  requireUserMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  notFound: vi.fn(),
  redirect: vi.fn(),
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/lib/api/server", () => ({
  getAssignments: getAssignmentsMock,
  getDashboard: getDashboardMock,
  getExcellentSubmission: getExcellentSubmissionMock,
  getAssignment: getAssignmentMock,
  getAssignmentSubmission: getAssignmentSubmissionMock,
  requireUser: requireUserMock,
}));

const student: User = {
  id: "student-id",
  email: "student@connect.hkust-gz.edu.cn",
  student_number: "20260001",
  full_name: "测试学生",
  role: "student",
  status: "active",
  cohort: null,
  direction: null,
  email_verified_at: "2026-08-24T00:00:00Z",
  created_at: "2026-08-24T00:00:00Z",
  revision: 1,
};

const dashboard: Dashboard = {
  current_user: {
    id: student.id,
    full_name: student.full_name,
    role: "student",
    cohort_id: null,
    direction_id: null,
  },
  unread_count: 0,
  unread_counts: {
    announcements: 0,
    assignments: 0,
    teams: 0,
    help_requests: 0,
  },
  recent_announcements: [],
  assignments: [],
  team: null,
};

describe("assignment pages", () => {
  beforeEach(() => {
    requireUserMock.mockResolvedValue(student);
    getDashboardMock.mockResolvedValue(dashboard);
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-08-29T12:00:00Z"));
    getAssignmentsMock.mockReset();
    getExcellentSubmissionMock.mockReset();
    getAssignmentMock.mockReset();
    getAssignmentSubmissionMock.mockReset();
  });

  it("shows submit and completion state without deadlines", async () => {
    const page: AssignmentPage = {
      items: [
        {
          id: "assignment-1",
          title: "数据结构作业",
          status: "published",
          can_submit: true,
          latest_submission: {
            submission_id: "submission-1",
            latest_version_id: "version-2",
            latest_version_number: 2,
            submitted_at: "2026-08-24T00:00:00Z",
            has_feedback: false,
            is_completed: false,
            completed_at: null,
          },
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
    };
    getAssignmentsMock.mockResolvedValue(page);

    render(
      await AssignmentsPage({
        searchParams: Promise.resolve({ status: "all" }),
      }),
    );

    expect(screen.getByText("可提交")).toBeInTheDocument();
    expect(screen.queryByText(/个人延期|修正截止|公共截止/)).not.toBeInTheDocument();
    expect(screen.getByText("已提交 v2")).toBeInTheDocument();
    expect(screen.getByText("未完成")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /数据结构作业/ })).toHaveAttribute(
      "href",
      "/assignments/assignment-1",
    );
  });

  it.each([
    [false, "未完成"],
    [true, "已完成"],
  ])("shows current-version completion %s on list and detail", async (isCompleted, label) => {
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-09-01T12:00:00Z"));
    const summary: AssignmentPage["items"][number] = {
      id: "assignment-1", title: "修正作业", status: "closed", can_submit: false,
      latest_submission: {
        submission_id: "submission-1", latest_version_id: "version-2", latest_version_number: 2,
        submitted_at: "2026-08-29T12:00:00Z", has_feedback: false,
        is_completed: isCompleted, completed_at: isCompleted ? "2026-08-30T10:00:00Z" : null,
      },
    };
    getAssignmentsMock.mockResolvedValue({ items: [summary], page: 1, page_size: 20, total: 1 });
    getAssignmentMock.mockResolvedValue({
      ...summary, description_html: "<p>作业说明</p>", training_url: null,
      submission_instructions: "完成练习", allowed_extensions: ["pdf"],
      max_total_bytes: 1024, excellent_submissions: [],
    });
    getAssignmentSubmissionMock.mockResolvedValue(null);
    const list = render(await AssignmentsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getAllByText("已关闭").length).toBeGreaterThan(0);
    list.unmount();
    render(await AssignmentDetailPage({ params: Promise.resolve({ assignmentId: summary.id }) }));
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getAllByText(/已关闭/).length).toBeGreaterThan(0);
  });

  it("never renders private feedback on an excellent source-version page", async () => {
    const excellent = {
      assignment_id: "assignment-1",
      assignment_title: "数据结构作业",
      version_id: "version-2",
      version_number: 2,
      author_name: "优秀同学",
      text_html: "<p>公开源版本正文</p>",
      external_url: null,
      submitted_at: "2026-08-24T00:00:00Z",
      marked_at: "2026-08-25T00:00:00Z",
      attachments: [],
      feedback: { body_html: "<p>绝密评语，不得公开</p>" },
    } as ExcellentSubmissionDetail & {
      feedback: { body_html: string };
    };
    getExcellentSubmissionMock.mockResolvedValue(excellent);

    render(
      await ExcellentSubmissionPage({
        params: Promise.resolve({
          assignmentId: "assignment-1",
          versionId: "version-2",
        }),
      }),
    );

    expect(screen.getByText("公开源版本正文")).toBeInTheDocument();
    expect(
      screen.getByText(/不包含作者的评语或其他历史版本/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/绝密评语/)).not.toBeInTheDocument();
  });
  it("shows a published assignment in the dashboard recent list", async () => {
    getDashboardMock.mockResolvedValue({
      ...dashboard,
      assignments: [
        {
          id: "assignment-1",
          title: "电控第一次作业",
        },
      ],
    });

    render(await DashboardPage());

    expect(screen.getByRole("heading", { name: "近期作业" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /电控第一次作业/ })).toHaveAttribute(
      "href",
      "/assignments/assignment-1",
    );
    expect(screen.queryByText("当前没有已发布作业。")).not.toBeInTheDocument();
  });
});
