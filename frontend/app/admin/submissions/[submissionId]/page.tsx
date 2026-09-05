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

  const [assignment, excellent] = await Promise.all([
    getAdminAssignment(submission.assignment_id),
    getExcellentSubmissions(submission.assignment_id),
  ]);
  if (assignment === null) {
    notFound();
  }

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/dashboard"
        backLabel="返回管理概览"
        eyebrow="ADMIN / SUBMISSIONS / REVIEW"
        title="审阅个人提交"
        description="正式版本不可变；私密评语仅对个人提交者与管理员可见，优秀标记只属于对应作业。"
      />
      <SubmissionReview
        assignmentTitle={assignment.title}
        initialExcellent={excellent}
        initialSubmission={submission}
      />
    </AppShell>
  );
}
