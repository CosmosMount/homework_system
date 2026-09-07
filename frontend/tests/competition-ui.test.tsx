import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminTeamCorrectionPanel } from "@/components/admin/team-correction-panel";
import { TeamEntryPanel } from "@/components/competitions/team-entry-panel";
import { TeamManagementPanel } from "@/components/competitions/team-management-panel";
import type { Team, TeamCreated, User } from "@/lib/api/types";

const { csrfFetchMock, pushMock, refreshMock, replaceMock } = vi.hoisted(() => ({
  csrfFetchMock: vi.fn(),
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/competitions",
  useRouter: () => ({
    push: pushMock,
    refresh: refreshMock,
    replace: replaceMock,
  }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  csrfFetch: csrfFetchMock,
}));

function team(overrides: Partial<Team> = {}): Team {
  return {
    id: "team-1",
    name: "第一队",
    status: "forming",
    captain_user_id: "student-1",
    member_count: 1,
    max_members: 4,
    dissolved_at: null,
    revision: 1,
    members: [
      {
        user_id: "student-1",
        full_name: "队长同学",
        student_number: "20260001",
        joined_at: "2026-08-25T00:00:00Z",
        added_by_admin: false,
        is_captain: true,
        direction_name: null,
        introduction: null,
      },
    ],
    can_manage: true,
    ...overrides,
  };
}

const candidate: User = {
  id: "student-2",
  email: "student2@connect.hkust-gz.edu.cn",
  student_number: "20260002",
  full_name: "候选同学",
  role: "student",
  status: "active",
  cohort: null,
  direction: null,
  email_verified_at: "2026-08-24T00:00:00Z",
  created_at: "2026-08-24T00:00:00Z",
  revision: 1,
};

describe("independent team UI", () => {
  beforeEach(() => {
    csrfFetchMock.mockReset();
    pushMock.mockReset();
    refreshMock.mockReset();
    replaceMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a team directly and preserves the one-time invite across refresh", async () => {
    const created: TeamCreated = {
      ...team(),
      invite_code: "A1B2C3D4E5F6",
    };
    csrfFetchMock.mockResolvedValue(created);

    render(<TeamEntryPanel hasTeam={false} />);
    fireEvent.change(screen.getByLabelText("队伍名称"), {
      target: { value: " 第一队 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建队伍" }));

    expect(await screen.findByText("A1B2C3D4E5F6")).toBeInTheDocument();
    expect(csrfFetchMock).toHaveBeenCalledWith("/teams", {
      method: "POST",
      body: JSON.stringify({ name: "第一队" }),
    });
    expect(refreshMock).toHaveBeenCalledOnce();
    expect(screen.getByText(/邀请码只显示这一次/)).toBeInTheDocument();
  });

  it("joins a team directly with an invite code", async () => {
    csrfFetchMock.mockResolvedValue(team({ member_count: 2 }));
    render(<TeamEntryPanel hasTeam={false} />);
    fireEvent.change(screen.getByLabelText("邀请码"), {
      target: { value: " JOIN-CODE " },
    });
    fireEvent.click(screen.getByRole("button", { name: "加入队伍" }));

    expect(await screen.findByText("已加入队伍。")).toBeInTheDocument();
    expect(csrfFetchMock).toHaveBeenCalledWith("/teams/join", {
      method: "POST",
      body: JSON.stringify({ invite_code: "JOIN-CODE" }),
    });
  });

  it("automatically assigns a team without a competition", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue({
      ...team({ id: "team-auto", name: "自动队" }),
      assignment: "created",
      invite_code: "AUTO-CODE-123",
    });

    render(<TeamEntryPanel hasTeam={false} />);
    fireEvent.click(screen.getByRole("button", { name: "自动分配队伍" }));

    expect(await screen.findByText("AUTO-CODE-123")).toBeInTheDocument();
    expect(csrfFetchMock).toHaveBeenCalledWith("/teams/auto-assign", {
      method: "POST",
    });
  });

  it("returns a member to the team center after leaving", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue({ status: "ok" });
    const memberTeam = team({
      captain_user_id: "student-1",
      member_count: 2,
      members: [
        ...team().members,
        {
          user_id: "student-2",
          full_name: "候选同学",
          student_number: "20260002",
          joined_at: "2026-08-25T01:00:00Z",
          added_by_admin: false,
          is_captain: false,
          direction_name: null,
          introduction: null,
        },
      ],
    });

    render(<TeamManagementPanel currentUserId="student-2" initialTeam={memberTeam} />);
    fireEvent.click(screen.getByRole("button", { name: "退出队伍" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/teams/team-1/members/student-2",
      { method: "DELETE" },
    );
    expect(pushMock).toHaveBeenCalledWith("/competitions");
  });

  it("requires a reason before deleting a team and permanently deletes it", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue(undefined);
    render(
      <AdminTeamCorrectionPanel initialTeam={team()} users={[candidate]} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "删除队伍" }));
    expect(screen.getByText("管理员纠错必须填写原因。")).toBeInTheDocument();
    expect(csrfFetchMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("必填原因"), {
      target: { value: " 删除重复创建的队伍 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "删除队伍" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("永久删除"));
    expect(csrfFetchMock).toHaveBeenCalledWith("/admin/teams/team-1", {
      method: "DELETE",
      body: JSON.stringify({ reason: "删除重复创建的队伍" }),
    });
    expect(replaceMock).toHaveBeenCalledWith("/admin/competitions");
  });
});
