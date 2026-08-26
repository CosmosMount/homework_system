import { notFound } from "next/navigation";

import { AdminPageHeader } from "@/components/admin/admin-page-header";

import { AssignmentEditor } from "@/components/admin/assignment-editor";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminAssignment,
  getAdminAssignmentSubmissions,
  getDirections,
  requireAdmin,
} from "@/lib/api/server";

type EditAssignmentPageProps = Readonly<{
  params: Promise<{ assignmentId: string }>;
}>;

export default async function EditAssignmentPage({
  params,
}: EditAssignmentPageProps) {
  const { assignmentId } = await params;
  const [admin, assignment, directions] = await Promise.all([
    requireAdmin(),
    getAdminAssignment(assignmentId),
    getDirections(),
  ]);
  if (assignment === null) {
    notFound();
  }
  const submissions =
    assignment.status === "draft"
      ? { items: [] }
      : await getAdminAssignmentSubmissions(assignmentId);

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/assignments"
        backLabel="返回作业管理"
        eyebrow="ADMIN / ASSIGNMENTS / EDIT"
        title="编辑作业"
        description="修改使用 revision；受众快照、正式版本和私密评语均由后端最终授权。"
      />
      <AssignmentEditor
        directions={directions}
        initialAssignment={assignment}
        initialSubmissions={submissions.items}
      />
    </AppShell>
  );
}
