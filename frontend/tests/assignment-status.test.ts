import { describe, expect, it } from "vitest";

import { assignmentSubmissionLabel } from "@/lib/assignment-status";
import type { AssignmentSummary } from "@/lib/api/types";

const assignment: AssignmentSummary = {
  id: "assignment", title: "作业", status: "published", can_submit: true,
  latest_submission: {
    submission_id: "submission", latest_version_id: "version", latest_version_number: 2,
    submitted_at: "2026-09-27T00:00:00Z", has_feedback: true,
    is_completed: false, completed_at: null,
  },
};

describe("作业提交状态", () => {
  it("uses server authorization and explicit close state", () => {
    expect(assignmentSubmissionLabel(assignment)).toBe("可提交");
    expect(assignmentSubmissionLabel({ ...assignment, status: "closed", can_submit: false })).toBe("已关闭");
    expect(assignmentSubmissionLabel({ ...assignment, status: "archived", can_submit: false })).toBe("当前只读");
  });
  it("does not mix completion with submission eligibility", () => {
    expect(assignmentSubmissionLabel({
      ...assignment,
      latest_submission: { ...assignment.latest_submission!, is_completed: true, completed_at: "2026-09-27T00:30:00Z" },
    })).toBe("可提交");
  });
});
