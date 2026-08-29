import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PublicHelpRequestDetailPage from "@/app/help/public/[requestId]/page";
import ProfilePage from "@/app/profile/page";
import SessionsPage from "@/app/sessions/page";
import type { Dashboard, PublicHelpRequestDetail, User } from "@/lib/api/types";

const {
  getDashboardMock,
  getPublicHelpRequestMock,
  getSessionsMock,
  requireUserMock,
} = vi.hoisted(() => ({
  getDashboardMock: vi.fn(),
  getPublicHelpRequestMock: vi.fn(),
  getSessionsMock: vi.fn(),
  requireUserMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  usePathname: () => "/profile",
  useRouter: () => ({
    push: vi.fn(),
    refresh: vi.fn(),
    replace: vi.fn(),
  }),
}));

vi.mock("@/lib/api/server", () => ({
  getDashboard: getDashboardMock,
  getPublicHelpRequest: getPublicHelpRequestMock,
  getSessions: getSessionsMock,
  requireUser: requireUserMock,
}));

const student: User = {
  id: "student-1",
  email: "student@connect.hkust-gz.edu.cn",
  student_number: "20260001",
  full_name: "测试学生",
  role: "student",
  status: "active",
  cohort: null,
  direction: null,
  email_verified_at: "2026-08-28T00:00:00Z",
  created_at: "2026-08-28T00:00:00Z",
  revision: 1,
};

const dashboard: Dashboard = {
  current_user: {
    id: student.id,
    full_name: student.full_name,
    role: student.role,
    cohort_id: null,
    direction_id: null,
  },
  unread_count: 10,
  unread_counts: {
    announcements: 1,
    assignments: 2,
    competitions: 3,
    help_requests: 4,
  },
  recent_announcements: [],
  assignments: [],
  competitions: [],
};

const publicHelpRequest: PublicHelpRequestDetail = {
  id: "help-1",
  request_type: "question",
  status: "resolved",
  title: "如何选择培训方向？",
  content_html: "<p>问题内容</p>",
  resolution_html: "<p>管理员答复</p>",
  created_at: "2026-08-28T01:00:00Z",
  updated_at: "2026-08-28T02:00:00Z",
  resolved_at: "2026-08-28T02:00:00Z",
  revision: 2,
};

describe("student shared page navigation", () => {
  beforeEach(() => {
    getDashboardMock.mockReset();
    getPublicHelpRequestMock.mockReset();
    getSessionsMock.mockReset();
    requireUserMock.mockReset();
    requireUserMock.mockResolvedValue(student);
    getDashboardMock.mockResolvedValue(dashboard);
    getPublicHelpRequestMock.mockResolvedValue(publicHelpRequest);
    getSessionsMock.mockResolvedValue([]);
  });

  it("keeps categorized unread badges on profile, session, and public help pages", async () => {
    const profile = render(await ProfilePage());
    expect(
      screen.getByRole("link", { name: "反馈答疑，4 条未读" }),
    ).toHaveAttribute("href", "/help");
    profile.unmount();

    const sessions = render(await SessionsPage());
    expect(
      screen.getByRole("link", { name: "通知，1 条未读" }),
    ).toHaveAttribute("href", "/announcements");
    sessions.unmount();

    render(
      await PublicHelpRequestDetailPage({
        params: Promise.resolve({ requestId: publicHelpRequest.id }),
      }),
    );
    expect(
      screen.getByRole("link", { name: "作业，2 条未读" }),
    ).toHaveAttribute("href", "/assignments");
    expect(getDashboardMock).toHaveBeenCalledTimes(3);
  });
});
