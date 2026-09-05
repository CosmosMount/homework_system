import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompetitionsPage from "@/app/competitions/page";
import type { Dashboard, TeamDirectoryPage, User } from "@/lib/api/types";

const {
  getDashboardMock,
  getMyTeamMock,
  getTeamsMock,
  requireUserMock,
} = vi.hoisted(() => ({
  getDashboardMock: vi.fn(),
  getMyTeamMock: vi.fn(),
  getTeamsMock: vi.fn(),
  requireUserMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  usePathname: () => "/competitions",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/api/server", () => ({
  getDashboard: getDashboardMock,
  getMyTeam: getMyTeamMock,
  getTeams: getTeamsMock,
  requireUser: requireUserMock,
}));

const student: User = {
  id: "student-1",
  email: "student1@connect.hkust-gz.edu.cn",
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

const teams: TeamDirectoryPage = {
  items: [
    {
      id: "team-1",
      name: "原子队",
      status: "forming",
      member_count: 2,
      max_members: 4,
      can_join: true,
    },
  ],
  total: 1,
  page: 2,
  page_size: 20,
};

describe("student campus team center", () => {
  beforeEach(() => {
    requireUserMock.mockResolvedValue(student);
    getDashboardMock.mockResolvedValue(dashboard);
    getMyTeamMock.mockResolvedValue(null);
    getTeamsMock.mockResolvedValue(teams);
  });

  it("allows direct team entry and searches the independent team directory", async () => {
    render(
      await CompetitionsPage({
        searchParams: Promise.resolve({ q: " 原子 ", page: "2" }),
      }),
    );

    expect(screen.getByRole("heading", { name: "校内赛队伍中心" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建队伍" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "加入队伍" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "自动分配队伍" })).toBeInTheDocument();
    expect(screen.getByText("原子队")).toBeInTheDocument();
    expect(screen.queryByText(/尚未配置校内赛/)).not.toBeInTheDocument();
    expect(getMyTeamMock).toHaveBeenCalledOnce();
    expect(getTeamsMock).toHaveBeenCalledWith(
      "query=%E5%8E%9F%E5%AD%90&page=2&page_size=20",
    );
    expect(screen.getByText("为保护隐私，目录不显示邀请码和成员姓名。")).toBeInTheDocument();
  });
});
