import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminCompetitionRegistrationPanel } from "@/components/admin/competition-registration-panel";
import { SubmissionReview } from "@/components/admin/submission-review";
import { AdminTeamCorrectionPanel } from "@/components/admin/team-correction-panel";
import { CompetitionSubmissionForm } from "@/components/assignments/submission-form";
import { CompetitionRegistrationActions } from "@/components/competitions/registration-actions";
import type {
  AdminRegistrationItem,
  AdminTeamDetail,
  CompetitionDetail,
  Submission,
  Team,
  TeamCreated,
  User,
} from "@/lib/api/types";

const { csrfFetchMock, pushMock, refreshMock } = vi.hoisted(() => ({
  csrfFetchMock: vi.fn(),
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({
    push: pushMock,
    refresh: refreshMock,
    replace: vi.fn(),
  }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  csrfFetch: csrfFetchMock,
}));

function competition(
  overrides: Partial<CompetitionDetail> = {},
): CompetitionDetail {
  return {
    id: "competition-1",
    name: "新生校内赛",
    description_markdown: "赛事说明",
    description_html: "<p>赛事说明</p>",
    rules_url: null,
    status: "registration_open",
    registration_start: "2026-08-25T00:00:00Z",
    registration_end: "2026-08-26T00:00:00Z",
    submission_start: "2026-08-27T00:00:00Z",
    submission_end: "2026-08-30T00:00:00Z",
    min_team_size: 2,
    max_team_size: 4,
    published_at: "2026-08-24T00:00:00Z",
    archived_at: null,
    revision: 1,
    registration_status: null,
    registration_disqualification_reason: null,
    team_id: null,
    team_name: null,
    team_status: null,
    tasks: [],
    ...overrides,
  };
}

function team(overrides: Partial<Team> = {}): Team {
  return {
    id: "team-1",
    competition_id: "competition-1",
    name: "第一队",
    status: "forming",
    captain_user_id: "student-1",
    member_count: 1,
    min_team_size: 2,
    max_team_size: 4,
    min_size_waived: false,
    waiver_reason: null,
    disqualification_reason: null,
    locked_at: null,
    dissolved_at: null,
    revision: 1,
    members: [
      {
        user_id: "student-1",
        full_name: "队长同学",
        student_id: "20260001",
        joined_at: "2026-08-25T00:00:00Z",
        added_by_admin: false,
        is_captain: true,
      },
    ],
    can_manage: true,
    can_submit: false,
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

function teamSubmission(): Submission {
  return {
    id: "submission-1",
    assignment_id: null,
    competition_task_id: "task-1",
    owner_user_id: null,
    owner_team_id: "team-1",
    latest_version_id: "version-1",
    versions: [
      {
        id: "version-1",
        submission_id: "submission-1",
        version_number: 1,
        submitted_by: "student-1",
        text_html: "<p>团队作品</p>",
        external_url: null,
        total_file_bytes: 0,
        submitted_at: "2026-08-27T00:00:00Z",
        attachments: [],
        feedback: null,
      },
    ],
  };
}

describe("competition UI", () => {
  beforeEach(() => {
    csrfFetchMock.mockReset();
    pushMock.mockReset();
    refreshMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("registers, creates a team, and shows the invite code only from the create response", async () => {
    const created: TeamCreated = {
      ...team(),
      invite_code: "A1B2C3D4E5F6",
    };
    csrfFetchMock
      .mockResolvedValueOnce({
        competition_id: "competition-1",
        user_id: "student-1",
        status: "registered",
        registered_at: "2026-08-25T00:00:00Z",
        withdrawn_at: null,
        disqualified_at: null,
        disqualification_reason: null,
        revision: 1,
      })
      .mockResolvedValueOnce(created);

    render(<CompetitionRegistrationActions competition={competition()} />);
    fireEvent.click(screen.getByRole("button", { name: "报名参赛" }));
    await screen.findByRole("button", { name: "创建并成为队长" });
    fireEvent.change(screen.getByLabelText("队伍名称"), {
      target: { value: "第一队" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建并成为队长" }));

    await screen.findByText("A1B2C3D4E5F6");
    expect(csrfFetchMock.mock.calls[0]).toEqual([
      "/competitions/competition-1/registration",
      { method: "POST" },
    ]);
    expect(csrfFetchMock.mock.calls[1]?.[0]).toBe(
      "/competitions/competition-1/teams",
    );
    expect(JSON.parse(String(csrfFetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      name: "第一队",
    });
    expect(screen.getByText(/离开页面后无法再次读取/)).toBeInTheDocument();
  });

  it("joins a team with a one-time invite input", async () => {
    csrfFetchMock.mockResolvedValue(team({ member_count: 2 }));
    render(
      <CompetitionRegistrationActions
        competition={competition({ registration_status: "registered" })}
      />,
    );
    fireEvent.change(screen.getByLabelText("邀请码"), {
      target: { value: "JOIN-CODE" },
    });
    fireEvent.click(screen.getByRole("button", { name: "加入队伍" }));

    await screen.findByText("第一队");
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/competitions/competition-1/teams/join",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(String(csrfFetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      invite_code: "JOIN-CODE",
    });
  });

  it("posts a captain team version to the competition endpoint", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000005",
    );
    csrfFetchMock.mockResolvedValue({
      submission_id: "submission-1",
      version_id: "version-1",
      version_number: 1,
      submitted_at: "2026-08-27T00:00:00Z",
      total_file_bytes: 0,
    });

    render(
      <CompetitionSubmissionForm
        allowedExtensions={["zip"]}
        competitionId="competition-1"
        maxTotalBytes={1024}
        taskId="task-1"
      />,
    );
    fireEvent.change(screen.getByLabelText("Markdown 文本"), {
      target: { value: "# 团队作品" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "确认并创建正式版本" }),
    );

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/competitions/competition-1/tasks/task-1/submission-versions",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Idempotency-Key": "00000000-0000-4000-8000-000000000005",
        },
      }),
    );
    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining("代表整个团队"),
    );
    expect(pushMock).toHaveBeenCalledWith(
      "/competitions/competition-1/tasks/task-1#version-version-1",
    );
  });

  it("requires a reason before any administrator team correction", () => {
    render(
      <AdminTeamCorrectionPanel
        initialTeam={{ ...team(), submissions: [] } as AdminTeamDetail}
        users={[candidate]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "豁免最小人数" }));

    expect(screen.getByText("管理员纠错必须填写原因。")).toBeInTheDocument();
    expect(csrfFetchMock).not.toHaveBeenCalled();
  });

  it("requires a private reason and warns before disqualifying a registered team member", async () => {
    const item: AdminRegistrationItem = {
      user_id: "student-1",
      full_name: "队长同学",
      student_number: "20260001",
      status: "registered",
      registered_at: "2026-08-25T00:00:00Z",
      withdrawn_at: null,
      disqualified_at: null,
      disqualification_reason: null,
      team_id: "team-1",
      team_name: "第一队",
    };
    const updated: AdminRegistrationItem = {
      ...item,
      status: "disqualified",
      disqualified_at: "2026-08-25T01:00:00Z",
      disqualification_reason: "资格材料不符合要求",
    };
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue(updated);
    render(
      <AdminCompetitionRegistrationPanel
        archived={false}
        competitionId="competition-1"
        initialRegistrations={[item]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "取消个人参赛资格" }),
    );
    expect(
      screen.getByText("取消个人参赛资格必须填写原因。"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("取消资格原因（队长同学）"), {
      target: { value: "资格材料不符合要求" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "取消个人参赛资格" }),
    );

    await screen.findByText("取消资格原因：资格材料不符合要求");
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("整队也会被取消资格"));
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/competitions/competition-1/registrations/student-1/disqualify",
      {
        method: "POST",
        body: JSON.stringify({ reason: "资格材料不符合要求" }),
      },
    );
  });

  it("never offers the excellent marker for a team submission", () => {
    render(
      <SubmissionReview
        assignmentTitle="赛事团队提交"
        initialExcellent={[]}
        initialSubmission={teamSubmission()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: /优秀标记|标记为优秀/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/TEAM SUBMISSION · NO SHOWCASE/)).toBeInTheDocument();
  });

  it("automatically joins the smallest available team", async () => {
    csrfFetchMock.mockResolvedValue({
      ...team({ id: "team-small", name: "人数较少队" }),
      assignment: "joined",
      invite_code: null,
    });
    render(
      <CompetitionRegistrationActions
        competition={competition({ registration_status: "registered" })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "没有队伍？自动分配" }));

    expect(await screen.findByText("已将你分配到人数较少的队伍。")).toBeInTheDocument();
    expect(screen.getByText("人数较少队")).toBeInTheDocument();
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/competitions/competition-1/auto-assign",
      { method: "POST" },
    );
  });

  it("shows the one-time invite when automatic assignment creates a team", async () => {
    csrfFetchMock.mockResolvedValue({
      ...team({ id: "team-auto", name: "自动组队-A1B2C3" }),
      assignment: "created",
      invite_code: "AUTO-CODE-123",
    });
    render(
      <CompetitionRegistrationActions
        competition={competition({ registration_status: "registered" })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "没有队伍？自动分配" }));

    expect(await screen.findByText("AUTO-CODE-123")).toBeInTheDocument();
    expect(screen.getByText(/邀请码只显示这一次/)).toBeInTheDocument();
  });
});
