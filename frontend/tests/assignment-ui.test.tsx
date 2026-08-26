import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SubmissionReview } from "@/components/admin/submission-review";
import { AssignmentSubmissionForm } from "@/components/assignments/submission-form";
import { AppShell } from "@/components/layout/app-shell";
import type { Feedback, Submission, User } from "@/lib/api/types";

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

const student: User = {
  id: "student-id",
  email: "student@connect.hkust-gz.edu.cn",
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

function submission(): Submission {
  return {
    id: "submission-1",
    assignment_id: "assignment-1",
    competition_task_id: null,
    owner_user_id: "student-id",
    owner_team_id: null,
    latest_version_id: "version-1",
    versions: [
      {
        id: "version-1",
        submission_id: "submission-1",
        version_number: 1,
        submitted_by: "student-id",
        text_html: "<p>作业正文</p>",
        external_url: null,
        total_file_bytes: 0,
        submitted_at: "2026-08-24T00:00:00Z",
        attachments: [],
        feedback: {
          id: "feedback-1",
          body_html: "<p>仅管理员和本人可见</p>",
          created_by: "admin-id",
          created_at: "2026-08-24T01:00:00Z",
          updated_at: "2026-08-24T01:00:00Z",
          revision: 3,
        },
      },
    ],
  };
}

describe("assignment UI", () => {
  beforeEach(() => {
    csrfFetchMock.mockReset();
    pushMock.mockReset();
    refreshMock.mockReset();
  });

  it("shows the student assignment navigation entry", () => {
    render(
      <AppShell user={student}>
        <p>内容</p>
      </AppShell>,
    );

    expect(screen.getByRole("link", { name: "作业" })).toHaveAttribute(
      "href",
      "/assignments",
    );
  });

  it("rejects an empty formal submission before confirmation", () => {
    const confirm = vi.spyOn(window, "confirm");

    render(
      <AssignmentSubmissionForm
        allowedExtensions={["pdf"]}
        assignmentId="assignment-1"
        maxTotalBytes={1024}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "确认并创建正式版本" }),
    );

    expect(
      screen.getByText("文本、外部链接和附件至少需要一种。"),
    ).toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();
    expect(csrfFetchMock).not.toHaveBeenCalled();
  });

  it("requires confirmation and sends an idempotency key for a formal version", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000001",
    );
    csrfFetchMock.mockResolvedValue({
      submission_id: "submission-1",
      version_id: "version-1",
      version_number: 1,
      submitted_at: "2026-08-24T00:00:00Z",
      total_file_bytes: 0,
    });

    render(
      <AssignmentSubmissionForm
        allowedExtensions={["pdf"]}
        assignmentId="assignment-1"
        maxTotalBytes={1024}
      />,
    );
    fireEvent.change(screen.getByLabelText("Markdown 文本"), {
      target: { value: "# 正式答案" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "确认并创建正式版本" }),
    );

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/assignments/assignment-1/submission-versions",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Idempotency-Key": "00000000-0000-4000-8000-000000000001",
        },
      }),
    );
    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining("正式版本不可修改或删除"),
    );
    expect(pushMock).toHaveBeenCalledWith(
      "/assignments/assignment-1/submissions/submission-1",
    );
  });

  it("sends the current feedback revision when an admin revises feedback", async () => {
    const updated: Feedback = {
      id: "feedback-1",
      body_html: "<p>修订后的私密评语</p>",
      created_by: "admin-id",
      created_at: "2026-08-24T01:00:00Z",
      updated_at: "2026-08-24T02:00:00Z",
      revision: 4,
    };
    csrfFetchMock.mockResolvedValue(updated);

    render(
      <SubmissionReview
        assignmentTitle="阶段作业"
        initialExcellent={[]}
        initialSubmission={submission()}
      />,
    );
    fireEvent.change(screen.getByLabelText("替换评语 Markdown"), {
      target: { value: "修订后的私密评语" },
    });
    fireEvent.click(screen.getByRole("button", { name: "修订评语" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    const request = csrfFetchMock.mock.calls[0];
    expect(request?.[0]).toBe(
      "/admin/submissions/submission-1/versions/version-1/feedback",
    );
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      body_markdown: "修订后的私密评语",
      revision: 3,
    });
  });
});
