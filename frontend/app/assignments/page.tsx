import Link from "next/link";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { buttonClassName, inputClassName } from "@/components/ui/form-controls";
import {
  getAssignments,
  getDashboard,
  requireUser,
} from "@/lib/api/server";
import { formatDateTime } from "@/lib/format";

type AssignmentsPageProps = Readonly<{
  searchParams: Promise<{
    q?: string;
    status?: string;
    page?: string;
  }>;
}>;

function pageHref(page: number, query: string, status: string): string {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (status !== "all") params.set("status", status);
  if (page > 1) params.set("page", String(page));
  const suffix = params.toString();
  return suffix ? "/assignments?" + suffix : "/assignments";
}

export default async function AssignmentsPage({
  searchParams,
}: AssignmentsPageProps) {
  const [user, dashboard, filters] = await Promise.all([
    requireUser(),
    getDashboard(),
    searchParams,
  ]);
  if (user.role === "admin") {
    redirect("/admin/assignments");
  }

  const query = (filters.q ?? "").trim().slice(0, 200);
  const statuses = new Set(["all", "pending", "submitted", "closed"]);
  const status = statuses.has(filters.status ?? "")
    ? (filters.status ?? "all")
    : "all";
  const requestedPage = Number(filters.page ?? "1");
  const page =
    Number.isSafeInteger(requestedPage) && requestedPage > 0
      ? requestedPage
      : 1;
  const apiParams = new URLSearchParams({
    page: String(page),
    page_size: "20",
    status,
  });
  if (query) apiParams.set("query", query);
  const assignments = await getAssignments(apiParams.toString());
  const hasNext = page * assignments.page_size < assignments.total;

  return (
    <AppShell unreadCount={dashboard.unread_count} user={user}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / ASSIGNMENTS
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">培训作业</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        列表按你的有效截止时间排序；个人延期会覆盖公共截止，历史受众以发布快照为准。
      </p>

      <form className="mt-8 grid gap-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 md:grid-cols-[minmax(0,1fr)_14rem_auto] md:items-end">
        <label className="text-sm font-medium">
          搜索作业
          <input
            className={inputClassName}
            defaultValue={query}
            maxLength={200}
            name="q"
            placeholder="输入标题关键词"
            type="search"
          />
        </label>
        <label className="text-sm font-medium">
          状态
          <select className={inputClassName} defaultValue={status} name="status">
            <option value="all">全部</option>
            <option value="pending">待提交</option>
            <option value="submitted">已提交</option>
            <option value="closed">已截止</option>
          </select>
        </label>
        <button
          className={buttonClassName}
          type="submit"
        >
          筛选
        </button>
      </form>

      <p className="mt-6 text-sm text-[var(--color-text-muted)]">
        共 {assignments.total} 项
      </p>
      {assignments.items.length ? (
        <div className="mt-4 space-y-3">
          {assignments.items.map((assignment) => (
            <Link
              className="block border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition hover:border-[var(--color-border-strong)]"
              href={"/assignments/" + assignment.id}
              key={assignment.id}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap gap-2 font-mono text-xs">
                    <span
                      className={
                        assignment.can_submit
                          ? "border border-[var(--color-success)] px-2 py-0.5 text-[var(--color-success)]"
                          : "border border-[var(--color-border-strong)] px-2 py-0.5"
                      }
                    >
                      {assignment.can_submit ? "可提交" : "只读"}
                    </span>
                    {assignment.has_personal_extension ? (
                      <span className="border border-[var(--color-info)] px-2 py-0.5 text-[var(--color-info)]">
                        个人延期
                      </span>
                    ) : null}
                    {assignment.latest_submission ? (
                      <span className="border border-[var(--color-accent)] px-2 py-0.5 text-[var(--color-accent-hover)]">
                        已提交 v
                        {assignment.latest_submission.latest_version_number}
                      </span>
                    ) : null}
                  </div>
                  <h2 className="mt-3 text-xl font-medium">{assignment.title}</h2>
                </div>
                <time
                  className="font-mono text-xs text-[var(--color-text-muted)]"
                  dateTime={assignment.effective_deadline}
                >
                  有效截止 {formatDateTime(assignment.effective_deadline)}
                </time>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <p className="mt-4 border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
          没有符合当前筛选条件的作业。
        </p>
      )}

      <nav aria-label="作业分页" className="mt-8 flex items-center justify-between">
        {page > 1 ? (
          <Link
            className="min-h-11 border border-[var(--color-border-strong)] px-5 py-2"
            href={pageHref(page - 1, query, status)}
          >
            ← 上一页
          </Link>
        ) : (
          <span />
        )}
        <span className="font-mono text-xs text-[var(--color-text-muted)]">
          第 {page} 页
        </span>
        {hasNext ? (
          <Link
            className="min-h-11 border border-[var(--color-border-strong)] px-5 py-2"
            href={pageHref(page + 1, query, status)}
          >
            下一页 →
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </AppShell>
  );
}
