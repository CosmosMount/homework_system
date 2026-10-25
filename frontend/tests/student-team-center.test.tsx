import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompetitionsPage from "@/app/competitions/page";
import { TeamDirectoryPanel } from "@/components/competitions/team-directory-panel";
import { TeamManagementPanel } from "@/components/competitions/team-management-panel";
import type { Dashboard, Team, TeamDirectoryPage, User } from "@/lib/api/types";

const {
  getDashboardMock,
  getMyTeamMock,
  getMyTeamApplicationsMock,
  getCaptainTeamApplicationsMock,
  getTeamSettingsMock,
  getTeamsMock,
  requireUserMock,
  csrfFetchMock,
  apiFetchMock,
} = vi.hoisted(() => ({
  getDashboardMock: vi.fn(),
  getMyTeamMock: vi.fn(),
  getMyTeamApplicationsMock: vi.fn(),
  getCaptainTeamApplicationsMock: vi.fn(),
  getTeamSettingsMock: vi.fn(),
  getTeamsMock: vi.fn(),
  requireUserMock: vi.fn(),
  csrfFetchMock: vi.fn(),
  apiFetchMock: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  csrfFetch: csrfFetchMock,
  apiFetch: apiFetchMock,
  ApiError: class ApiError extends Error {},
}));

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  usePathname: () => "/competitions",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/api/server", () => ({
  getDashboard: getDashboardMock,
  getMyTeam: getMyTeamMock,
  getMyTeamApplications: getMyTeamApplicationsMock,
  getCaptainTeamApplications: getCaptainTeamApplicationsMock,
  getTeamSettings: getTeamSettingsMock,
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
      can_apply: true,
    },
  ],
  total: 1,
  page: 2,
  page_size: 20,
};

describe("student campus team center", () => {
  beforeEach(() => {
    csrfFetchMock.mockReset();
    apiFetchMock.mockReset();
    requireUserMock.mockResolvedValue(student);
    getDashboardMock.mockResolvedValue(dashboard);
    getMyTeamMock.mockResolvedValue(null);
    getMyTeamApplicationsMock.mockResolvedValue([]);
    getCaptainTeamApplicationsMock.mockResolvedValue([]);
    getTeamSettingsMock.mockResolvedValue({
      is_team_open: true,
      updated_at: "2026-09-08T00:00:00Z",
      revision: 1,
    });
    getTeamsMock.mockResolvedValue(teams);
  });

  it("submits one application from the directory and marks the target pending", async () => {
    csrfFetchMock.mockResolvedValue({ id: "application-1" });
    render(<TeamDirectoryPanel initialTeams={teams} query="" currentTeamId={null} initialApplications={[]} />);

    fireEvent.click(screen.getByRole("button", { name: "申请加入" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledWith("/teams/team-1/applications", { method: "POST" }));
    expect(screen.getByRole("button", { name: "已申请" })).toBeDisabled();
  });

  it("lets the captain rename and approve an application", async () => {
    const team: Team = {
      id: "team-1", name: "原子队", status: "forming", captain_user_id: student.id,
      member_count: 1, max_members: 5, dissolved_at: null, revision: 1,
      captain_email: "captain@connect.hkust-gz.edu.cn", contact_wechat: null,
      members: [{ user_id: student.id, full_name: student.full_name, student_number: student.student_number,
        joined_at: "2026-09-08T00:00:00Z", added_by_admin: false, is_captain: true,
        direction_name: "机械", introduction: null }], can_manage: true,
    };
    const confirmation = vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValueOnce({ ...team, name: "新队名", revision: 2 }).mockResolvedValueOnce({});
    apiFetchMock.mockResolvedValue({ ...team, name: "新队名", revision: 3, member_count: 2 });
    render(<TeamManagementPanel initialTeam={team} currentUserId={student.id} initialApplications={[
      { id: "application-1", team_id: team.id, team_name: team.name, applicant_user_id: "student-2",
        applicant_full_name: "申请人", status: "pending", created_at: "2026-09-08T00:00:00Z", responded_at: null },
    ]} />);

    fireEvent.change(screen.getByLabelText("队伍名称"), { target: { value: "新队名" } });
    fireEvent.click(screen.getByRole("button", { name: "更改队名" }));
    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledWith("/teams/team-1/name", {
      method: "PATCH", body: JSON.stringify({ name: "新队名", revision: 1 }),
    }));
    fireEvent.click(screen.getByRole("button", { name: "同意" }));
    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledWith(
      "/teams/team-1/applications/application-1/accept", { method: "POST" },
    ));
    confirmation.mockRestore();
  });

  it("allows direct team entry and searches the independent team directory", async () => {
    render(
      await CompetitionsPage({
        searchParams: Promise.resolve({ q: " 原子 ", page: "2" }),
      }),
    );

    expect(screen.getByRole("heading", { name: "校内赛队伍中心" })).toBeInTheDocument();
    expect(screen.getByText(/机械 1～2 人 \+ 嵌入式控制 1 人 \+ 嵌入式硬件 1 人 \+ 算法 1 人，共 4～5 人/)).toBeInTheDocument();
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
