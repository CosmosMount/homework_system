import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminCompetitionsPage from "@/app/admin/competitions/page";
import type { CompetitionPage, User } from "@/lib/api/types";

const {
  getAdminCompetitionTeamsMock,
  getAdminCompetitionsMock,
  requireAdminMock,
} = vi.hoisted(() => ({
  getAdminCompetitionTeamsMock: vi.fn(),
  getAdminCompetitionsMock: vi.fn(),
  requireAdminMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/competitions",
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/api/server", () => ({
  getAdminCompetitionTeams: getAdminCompetitionTeamsMock,
  getAdminCompetitions: getAdminCompetitionsMock,
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
  revision: 1,
};

const competitions: CompetitionPage = {
  items: [
    {
      id: "competition-1",
      name: "2026 校内赛",
      status: "registration_open",
      registration_start: "2026-08-20T00:00:00Z",
      registration_end: "2026-09-01T00:00:00Z",
      submission_start: "2026-09-01T00:00:00Z",
      submission_end: "2026-09-15T00:00:00Z",
      min_team_size: 2,
      max_team_size: 4,
      registration_status: null,
      registration_disqualification_reason: null,
      team_id: null,
      team_name: null,
      team_status: null,
    },
  ],
  total: 1,
  page: 1,
  page_size: 100,
};

describe("admin campus competition page", () => {
  beforeEach(() => {
    requireAdminMock.mockResolvedValue(admin);
    getAdminCompetitionsMock.mockResolvedValue(competitions);
    getAdminCompetitionTeamsMock.mockResolvedValue({
      total: 1,
      items: [
        {
          id: "team-1",
          competition_id: "competition-1",
          name: "原子队",
          status: "forming",
          captain_user_id: "student-1",
          member_count: 3,
          min_size_waived: false,
          latest_submission_count: 0,
        },
      ],
    });
  });

  it("shows the current campus competition and teams without a create action", async () => {
    render(await AdminCompetitionsPage());

    expect(screen.getByRole("heading", { name: "校内赛" })).toBeInTheDocument();
    expect(screen.getByText("原子队")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "管理公告" })).toHaveAttribute(
      "href",
      "/admin/competitions/competition-1",
    );
    expect(screen.queryByText("新建赛事")).not.toBeInTheDocument();
    expect(screen.queryByText("新建校内赛")).not.toBeInTheDocument();
  });
});
