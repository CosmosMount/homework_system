import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminCompetitionsPage from "@/app/admin/competitions/page";
import type { AdminTeamList, User } from "@/lib/api/types";

const { getAdminTeamsMock, requireAdminMock } = vi.hoisted(() => ({
  getAdminTeamsMock: vi.fn(),
  requireAdminMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/competitions",
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/api/server", () => ({
  getAdminTeams: getAdminTeamsMock,
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

const teams: AdminTeamList = {
  total: 1,
  page: 1,
  page_size: 20,
  items: [
    {
      id: "team-1",
      name: "原子队",
      status: "forming",
      captain_user_id: "student-1",
      member_count: 3,
      max_members: 4,
    },
  ],
};

describe("admin campus team page", () => {
  beforeEach(() => {
    requireAdminMock.mockResolvedValue(admin);
    getAdminTeamsMock.mockResolvedValue(teams);
  });

  it("shows independent teams without competition creation or announcement controls", async () => {
    render(
      await AdminCompetitionsPage({
        searchParams: Promise.resolve({ q: "原子", page: "1" }),
      }),
    );

    expect(screen.getByRole("heading", { name: "校内赛队伍" })).toBeInTheDocument();
    expect(screen.getByText("原子队")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /原子队/ })).toHaveAttribute(
      "href",
      "/admin/competitions/team-1",
    );
    expect(screen.queryByText(/新建赛事|管理公告|报名/)).not.toBeInTheDocument();
    expect(getAdminTeamsMock).toHaveBeenCalledWith(
      "query=%E5%8E%9F%E5%AD%90&page=1&page_size=20",
    );
  });
});
