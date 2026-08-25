import { AssignmentEditor } from "@/components/admin/assignment-editor";
import { AppShell } from "@/components/layout/app-shell";
import { getCohorts, getDirections, requireAdmin } from "@/lib/api/server";

export default async function NewAssignmentPage() {
  const [admin, cohorts, directions] = await Promise.all([
    requireAdmin(),
    getCohorts(),
    getDirections(),
  ]);

  return (
    <AppShell user={admin}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ADMIN / ASSIGNMENTS / NEW
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">新建作业</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        发布事务会固化逐学生受众；发布后仅允许修正文案和延长截止。
      </p>
      <AssignmentEditor
        cohorts={cohorts}
        directions={directions}
        initialAssignment={null}
        initialSubmissions={[]}
      />
    </AppShell>
  );
}
