import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompetitionsPage from "@/app/competitions/page";
import type {
  CompetitionDetail,
  CompetitionPage,
  Dashboard,
  TeamDirectoryPage,
  User,
} from "@/lib/api/types";

const {
  getCompetitionMock,
  getCompetitionsMock,
  getCompetitionTeamsMock,
  getDashboardMock,
  requireUserMock,
} = vi.hoisted(() => ({
  getCompetitionMock: vi.fn(),
  getCompetitionsMock: vi.fn(),
  getCompetitionTeamsMock: vi.fn(),
  getDashboardMock: vi.fn(),
  requireUserMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  usePathname: () => "/competitions",
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/api/server", () => ({
  getCompetition: getCompetitionMock,
  getCompetitions: getCompetitionsMock,
  getCompetitionTeams: getCompetitionTeamsMock,
  getDashboard: getDashboardMock,
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
    competitions: 0,
    help_requests: 0,
  },
  recent_announcements: [],
  assignments: [],
  competitions: [],
};

const summaries: CompetitionPage = {
  items: [
    {
      id: "current-competition",
      name: "2026 校内赛",
      status: "registration_open",
      registration_start: "2026-08-20T00:00:00Z",
      registration_end: "2026-09-01T00:00:00Z",
      submission_start: "2026-09-01T00:00:00Z",
      submission_end: "2026-09-15T00:00:00Z",
      min_team_size: 2,
      max_team_size: 4,
      registration_status: "registered",
      registration_disqualification_reason: null,
      team_id: null,
      team_name: null,
      team_status: null,
    },
    {
      id: "archived-competition",
      name: "历史赛事",
      status: "archived",
      registration_start: "2025-08-20T00:00:00Z",
      registration_end: "2025-09-01T00:00:00Z",
      submission_start: "2025-09-01T00:00:00Z",
      submission_end: "2025-09-15T00:00:00Z",
      min_team_size: 2,
      max_team_size: 4,
      registration_status: null,
      registration_disqualification_reason: null,
      team_id: null,
      team_name: null,
      team_status: null,
    },
  ],
  total: 2,
  page: 1,
  page_size: 100,
};

const competition: CompetitionDetail = {
  id: "current-competition",
  name: "2026 校内赛",
  description_markdown: "公告",
  description_html: "<p>校内赛公告</p>",
  rules_url: null,
  status: "registration_open",
  registration_start: "2026-08-20T00:00:00Z",
  registration_end: "2026-09-01T00:00:00Z",
  submission_start: "2026-09-01T00:00:00Z",
  submission_end: "2026-09-15T00:00:00Z",
  min_team_size: 2,
  max_team_size: 4,
  published_at: "2026-08-19T00:00:00Z",
  archived_at: null,
  revision: 1,
  registration_status: "registered",
  registration_disqualification_reason: null,
  team_id: null,
  team_name: null,
  team_status: null,
  tasks: [],
};

const teams: TeamDirectoryPage = {
  items: [
    {
      id: "team-1",
      competition_id: competition.id,
      name: "原子队",
      status: "forming",
      member_count: 2,
      max_team_size: 4,
      can_join: true,
    },
  ],
  total: 1,
  page: 2,
  page_size: 20,
};

describe("student campus competition team center", () => {
  beforeEach(() => {
    requireUserMock.mockResolvedValue(student);
    getDashboardMock.mockResolvedValue(dashboard);
    getCompetitionsMock.mockResolvedValue(summaries);
    getCompetitionMock.mockResolvedValue(competition);
    getCompetitionTeamsMock.mockResolvedValue(teams);
  });

  it("shows only the current campus competition and searches its team directory", async () => {
    render(
      await CompetitionsPage({
        searchParams: Promise.resolve({ q: " 原子 ", page: "2" }),
      }),
    );

    expect(
      screen.getByRole("heading", { name: "校内赛队伍中心" }),
    ).toBeInTheDocument();
    expect(screen.getByText("校内赛公告")).toBeInTheDocument();
    expect(screen.getByText("原子队")).toBeInTheDocument();
    expect(screen.queryByText("历史赛事")).not.toBeInTheDocument();
    expect(getCompetitionMock).toHaveBeenCalledWith("current-competition");
    expect(getCompetitionTeamsMock).toHaveBeenCalledWith(
      "current-competition",
      "query=%E5%8E%9F%E5%AD%90&page=2&page_size=20",
    );
    expect(screen.getByText("为保护隐私，目录不显示邀请码和成员姓名。")).toBeInTheDocument();
  });
});
