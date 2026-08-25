import Link from "next/link";

import { AppShell } from "@/components/layout/app-shell";
import { buttonLinkClassName } from "@/components/ui/form-controls";
import { getAdminAssignments, requireAdmin } from "@/lib/api/server";
import { formatDateTime } from "@/lib/format";

export default async function AdminAssignmentsPage() {
  const [admin, assignments] = await Promise.all([
    requireAdmin(),
    getAdminAssignments(),
  ]);

  return (
    <AppShell user={admin}>
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
            ADMIN / ASSIGNMENTS
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">
            作业管理
          </h1>
          <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
            管理固定受众快照、公共截止、个人延期、提交统计与优秀版本。
          </p>
        </div>
        <Link
          className={buttonLinkClassName + " group shrink-0"}
          href="/admin/assignments/new"
        >
          <span aria-hidden="true" className="text-lg leading-none transition-transform group-hover:rotate-90">＋</span>
          <span>新建作业</span>
        </Link>
      </div>

      <div className="mt-8 space-y-3">
        {assignments.items.map((assignment) => (
          <Link
            className="block border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition hover:border-[var(--color-border-strong)]"
            href={"/admin/assignments/" + assignment.id + "/edit"}
            key={assignment.id}
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex flex-wrap gap-2 font-mono text-xs">
                  <span className="border border-[var(--color-border-strong)] px-2 py-0.5">
                    {assignment.status}
                  </span>
                  <span className="border border-[var(--color-info)] px-2 py-0.5 text-[var(--color-info)]">
                    {assignment.stats.submitted_count} /{" "}
                    {assignment.stats.target_count} 已提交
                  </span>
                </div>
                <h2 className="mt-3 text-xl font-medium">{assignment.title}</h2>
              </div>
              <time
                className="font-mono text-xs text-[var(--color-text-muted)]"
                dateTime={assignment.deadline}
              >
                截止 {formatDateTime(assignment.deadline)}
              </time>
            </div>
          </Link>
        ))}
        {assignments.items.length === 0 ? (
          <p className="border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
            尚未创建作业。
          </p>
        ) : null}
      </div>
    </AppShell>
  );
}
