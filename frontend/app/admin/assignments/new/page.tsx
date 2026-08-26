import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AssignmentEditor } from "@/components/admin/assignment-editor";
import { AppShell } from "@/components/layout/app-shell";
import { getDirections, requireAdmin } from "@/lib/api/server";

export default async function NewAssignmentPage() {
  const [admin, directions] = await Promise.all([
    requireAdmin(),
    getDirections(),
  ]);

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/assignments"
        backLabel="返回作业管理"
        eyebrow="ADMIN / ASSIGNMENTS / NEW"
        title="新建作业"
        description="发布事务会固化逐学生受众；发布后仅允许修正文案和延长截止。"
      />
      <AssignmentEditor
        directions={directions}
        initialAssignment={null}
        initialSubmissions={[]}
      />
    </AppShell>
  );
}
