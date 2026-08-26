import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompetitionTaskPage from "@/app/competitions/[competitionId]/tasks/[taskId]/page";
import type {
  CompetitionDetail,
  CompetitionTask,
  Dashboard,
  Team,
  User,
} from "@/lib/api/types";

const {
  getCompetitionMock,
  getCompetitionSubmissionMock,
  getCompetitionTaskMock,
  getCompetitionTeamMock,
  getDashboardMock,
  requireUserMock,
} = vi.hoisted(() => ({
  getCompetitionMock: vi.fn(),
  getCompetitionSubmissionMock: vi.fn(),
  getCompetitionTaskMock: vi.fn(),
  getCompetitionTeamMock: vi.fn(),
  getDashboardMock: vi.fn(),
  requireUserMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  notFound: vi.fn(),
  redirect: vi.fn(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/api/server", () => ({
  getCompetition: getCompetitionMock,
  getCompetitionSubmission: getCompetitionSubmissionMock,
  getCompetitionTask: getCompetitionTaskMock,
  getCompetitionTeam: getCompetitionTeamMock,
  getDashboard: getDashboardMock,
  requireUser: requireUserMock,
}));

const student: User = {
  id: "member-1",
  email: "member1@connect.hkust-gz.edu.cn",
  student_number: "20260001",
  full_name: "普通成员",
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
  recent_announcements: [],
  assignments: [],
  competitions: [],
};

const competition: CompetitionDetail = {
  id: "competition-1",
  name: "新生校内赛",
  description_markdown: "说明",
  description_html: "<p>说明</p>",
  rules_url: null,
  status: "submission_open",
  registration_start: "2026-08-20T00:00:00Z",
  registration_end: "2026-08-22T00:00:00Z",
  submission_start: "2026-08-23T00:00:00Z",
  submission_end: "2099-08-30T00:00:00Z",
  min_team_size: 2,
  max_team_size: 4,
  published_at: "2026-08-19T00:00:00Z",
  archived_at: null,
  revision: 3,
  registration_status: "registered",
  registration_disqualification_reason: null,
  team_id: "team-1",
  team_name: "第一队",
  team_status: "locked",
  tasks: [],
};

const task: CompetitionTask = {
  id: "task-1",
  competition_id: competition.id,
  title: "团队交付",
  description_markdown: "题面",
  description_html: "<p>题面</p>",
  resource_url: null,
  allowed_extensions: ["zip"],
  max_total_bytes: 1024,
  deadline: "2099-08-29T00:00:00Z",
  display_order: 0,
  revision: 1,
  submission_id: null,
  latest_version_id: null,
};

const team: Team = {
  id: "team-1",
  competition_id: competition.id,
  name: "第一队",
  status: "locked",
  captain_user_id: "captain-1",
  member_count: 2,
  min_team_size: 2,
  max_team_size: 4,
  min_size_waived: false,
  waiver_reason: null,
  disqualification_reason: null,
  locked_at: "2026-08-22T00:00:00Z",
  dissolved_at: null,
  revision: 2,
  members: [
    {
      user_id: "captain-1",
      full_name: "队长",
      student_id: "20260002",
      joined_at: "2026-08-20T00:00:00Z",
      added_by_admin: false,
      is_captain: true,
    },
    {
      user_id: student.id,
      full_name: student.full_name,
      student_id: student.student_number,
      joined_at: "2026-08-20T01:00:00Z",
      added_by_admin: false,
      is_captain: false,
    },
  ],
  can_manage: false,
  can_submit: false,
};

describe("competition task page", () => {
  beforeEach(() => {
    requireUserMock.mockResolvedValue(student);
    getDashboardMock.mockResolvedValue(dashboard);
    getCompetitionMock.mockResolvedValue(competition);
    getCompetitionTaskMock.mockResolvedValue(task);
    getCompetitionTeamMock.mockResolvedValue(team);
    getCompetitionSubmissionMock.mockResolvedValue(null);
  });

  it("keeps a normal team member read-only while allowing version history access", async () => {
    render(
      await CompetitionTaskPage({
        params: Promise.resolve({
          competitionId: competition.id,
          taskId: task.id,
        }),
      }),
    );

    expect(
      screen.getByText(/只有当前队长可以代表团队创建正式版本/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "确认并创建正式版本" }),
    ).not.toBeInTheDocument();
  });
});
