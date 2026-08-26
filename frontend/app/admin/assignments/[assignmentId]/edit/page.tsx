import { notFound } from "next/navigation";

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
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / ASSIGNMENTS / EDIT
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">编辑作业</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        修改使用 revision；受众快照、正式版本和私密评语均由后端最终授权。
      </p>
      <AssignmentEditor
        directions={directions}
        initialAssignment={assignment}
        initialSubmissions={submissions.items}
      />
    </AppShell>
  );
}
