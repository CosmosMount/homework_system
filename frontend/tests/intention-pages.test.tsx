import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IntentionDetailPage from "@/app/intentions/[surveyId]/page";
import type { Dashboard, IntentionSurvey, User } from "@/lib/api/types";

const { getDashboardMock, getIntentionMock, requireUserMock } = vi.hoisted(() => ({
  getDashboardMock: vi.fn(),
  getIntentionMock: vi.fn(),
  requireUserMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  usePathname: () => "/intentions/survey-1",
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/api/server", () => ({
  getDashboard: getDashboardMock,
  getIntention: getIntentionMock,
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

const survey: IntentionSurvey = {
  id: "survey-1",
  title: "培训方向问卷",
  description_html: "<p>请选择</p>",
  status: "open",
  starts_at: null,
  ends_at: null,
  question_count: 1,
  has_response: false,
  submissions_used: 0,
  max_submissions: 1,
  questions: [
    {
      id: "question-1",
      prompt: "第一志愿",
      allow_multiple: false,
      display_order: 0,
      options: [{ id: "option-1", label: "机器人", display_order: 0 }],
    },
  ],
  response: null,
  revision: 1,
};

describe("intention QR detail page", () => {
  beforeEach(() => {
    requireUserMock.mockResolvedValue(student);
    getDashboardMock.mockResolvedValue(dashboard);
    getIntentionMock.mockResolvedValue(survey);
  });

  it("preserves the survey and QR token through the login guard", async () => {
    render(
      await IntentionDetailPage({
        params: Promise.resolve({ surveyId: "survey-1" }),
        searchParams: Promise.resolve({ token: "qr-token" }),
      }),
    );

    expect(requireUserMock).toHaveBeenCalledWith(
      "/intentions/survey-1?token=qr-token",
    );
    expect(getIntentionMock).toHaveBeenCalledWith("survey-1", "qr-token");
    expect(
      screen.getByRole("heading", { name: "培训方向问卷" }),
    ).toBeInTheDocument();
  });
});
