import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AssignmentSubmissionForm } from "@/components/assignments/submission-form";
import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAssignment,
  getAssignmentSubmission,
  getDashboard,
  requireUser,
} from "@/lib/api/server";
import { formatDateTime, formatFileSize } from "@/lib/format";

type AssignmentDetailPageProps = Readonly<{
  params: Promise<{ assignmentId: string }>;
}>;

export default async function AssignmentDetailPage({
  params,
}: AssignmentDetailPageProps) {
  const [{ assignmentId }, user, dashboard] = await Promise.all([
    params,
    requireUser(),
    getDashboard(),
  ]);
  if (user.role === "admin") {
    redirect("/admin/assignments/" + assignmentId + "/edit");
  }
  const [assignment, submission] = await Promise.all([
    getAssignment(assignmentId),
    getAssignmentSubmission(assignmentId),
  ]);
  if (assignment === null) {
    notFound();
  }

  return (
    <AppShell unreadCount={dashboard.unread_count} user={user}>
      <Link className="text-sm text-[var(--color-info)]" href="/assignments">
        ← 返回作业列表
      </Link>
      <article className="mt-6">
        <div className="grid gap-6 border-b border-[var(--color-border)] pb-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div>
            <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
              ASSIGNMENT / DETAIL
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              {assignment.title}
            </h1>
            <div className="mt-5 flex flex-wrap gap-2 font-mono text-xs">
              <span
                className={
                  assignment.can_submit
                    ? "border border-[var(--color-success)] px-2 py-1 text-[var(--color-success)]"
                    : "border border-[var(--color-border-strong)] px-2 py-1"
                }
              >
                {assignment.can_submit ? "当前可提交" : "当前只读"}
              </span>
              {assignment.has_personal_extension ? (
                <span className="border border-[var(--color-info)] px-2 py-1 text-[var(--color-info)]">
                  已获个人延期
                </span>
              ) : null}
            </div>
          </div>
          <dl className="space-y-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 text-sm">
            <div>
              <dt className="text-[var(--color-text-muted)]">公共截止</dt>
              <dd className="mt-1">{formatDateTime(assignment.public_deadline)}</dd>
            </div>
            <div>
              <dt className="text-[var(--color-text-muted)]">你的有效截止</dt>
              <dd className="mt-1 text-[var(--color-accent-hover)]">
                {formatDateTime(assignment.effective_deadline)}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--color-text-muted)]">附件限制</dt>
              <dd className="mt-1">
                {assignment.allowed_extensions.join(", ")} ·{" "}
                {formatFileSize(assignment.max_total_bytes)}
              </dd>
            </div>
          </dl>
        </div>

        <div className="mx-auto mt-8 max-w-4xl">
          <SafeHtml sanitizedHtml={assignment.description_html} />
          {assignment.training_url ? (
            <p className="mt-6">
              <a
                className="text-[var(--color-info)] underline underline-offset-4"
                href={assignment.training_url}
                rel="noopener noreferrer"
                target="_blank"
              >
                打开培训资料 ↗
              </a>
            </p>
          ) : null}
          <section className="mt-8 border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <h2 className="text-lg font-semibold">提交说明</h2>
            <p className="mt-3 whitespace-pre-wrap text-sm text-[var(--color-text-secondary)]">
              {assignment.submission_instructions}
            </p>
          </section>
        </div>
      </article>

      {submission ? (
        <section className="mx-auto mt-10 max-w-4xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold">你的提交历史</h2>
              <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                最新正式版本 v{submission.versions[0]?.version_number ?? "—"}，共{" "}
                {submission.versions.length} 个不可变版本。
              </p>
            </div>
            <Link
              className="min-h-11 border border-[var(--color-border-strong)] px-5 py-2"
              href={
                "/assignments/" +
                assignment.id +
                "/submissions/" +
                submission.id
              }
            >
              查看版本与私密评语
            </Link>
          </div>
        </section>
      ) : null}

      {assignment.can_submit ? (
        <div className="mx-auto max-w-4xl">
          <AssignmentSubmissionForm
            allowedExtensions={assignment.allowed_extensions}
            assignmentId={assignment.id}
            maxTotalBytes={assignment.max_total_bytes}
          />
        </div>
      ) : (
        <p className="mx-auto mt-10 max-w-4xl border border-dashed border-[var(--color-border-strong)] p-6 text-[var(--color-text-muted)]">
          当前已不能创建新版本；历史正式版本仍可查看和下载。
        </p>
      )}

      {assignment.excellent_submissions.length ? (
        <section className="mx-auto mt-12 max-w-4xl border-t border-[var(--color-border)] pt-7">
          <h2 className="text-2xl font-semibold">本作业优秀提交</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            仅展示管理员标记的源版本，不含私密评语和其他历史版本。
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {assignment.excellent_submissions.map((item) => (
              <Link
                className="border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
                href={
                  "/assignments/" +
                  assignment.id +
                  "/excellent-submissions/" +
                  item.version_id
                }
                key={item.version_id}
              >
                <p className="font-medium">{item.author_name}</p>
                <p className="mt-2 font-mono text-xs text-[var(--color-text-muted)]">
                  版本 v{item.version_number} · 标记于{" "}
                  {formatDateTime(item.marked_at)}
                </p>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
    </AppShell>
  );
}
