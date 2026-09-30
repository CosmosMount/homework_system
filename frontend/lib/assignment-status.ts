import type { AssignmentSummary } from "@/lib/api/types";

export function assignmentSubmissionLabel(
  assignment: AssignmentSummary,
): string {
  if (assignment.can_submit) return "可提交";
  if (assignment.status === "closed") return "已关闭";
  return "当前只读";
}
