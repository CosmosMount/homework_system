import { notFound } from "next/navigation";

import { AdminPageHeader } from "@/components/admin/admin-page-header";

import { SubmissionReview } from "@/components/admin/submission-review";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminAssignment,
  getExcellentSubmissions,
  getSubmission,
  requireAdmin,
} from "@/lib/api/server";
import type { ExcellentSubmissionSummary } from "@/lib/api/types";

type AdminSubmissionPageProps = Readonly<{
  params: Promise<{ submissionId: string }>;
}>;

export default async function AdminSubmissionPage({
  params,
}: AdminSubmissionPageProps) {
  const { submissionId } = await params;
  const [admin, submission] = await Promise.all([
    requireAdmin(),
    getSubmission(submissionId),
  ]);
  if (submission === null) {
    notFound();
  }

  let resourceTitle = "赛事团队提交";
  let excellent: ExcellentSubmissionSummary[] = [];
  if (submission.assignment_id !== null) {
    const [assignment, assignmentExcellent] = await Promise.all([
      getAdminAssignment(submission.assignment_id),
      getExcellentSubmissions(submission.assignment_id),
    ]);
    if (assignment === null) {
      notFound();
    }
    resourceTitle = assignment.title;
    excellent = assignmentExcellent;
  }

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/dashboard"
        backLabel="返回管理概览"
        eyebrow="ADMIN / SUBMISSIONS / REVIEW"
        title={submission.assignment_id === null ? "审阅团队提交" : "审阅个人提交"}
        description="正式版本不可变；私密评语仅对个人所有者或当前团队成员与管理员可见，赛事版本不提供优秀标记。"
      />
      <SubmissionReview
        assignmentTitle={resourceTitle}
        initialExcellent={excellent}
        initialSubmission={submission}
      />
    </AppShell>
  );
}
