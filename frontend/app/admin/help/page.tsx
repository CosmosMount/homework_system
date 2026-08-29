import Link from "next/link";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AppShell } from "@/components/layout/app-shell";
import { getAdminHelpRequests, requireAdmin } from "@/lib/api/server";
import type { HelpRequestStatus, HelpRequestType } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import {
  helpRequestStatusLabel,
  helpRequestTypeLabel,
} from "@/lib/help-request-labels";

type AdminHelpPageProps = Readonly<{
  searchParams: Promise<{
    type?: string;
    status?: string;
    query?: string;
    page?: string;
  }>;
}>;

function requestType(value: string | undefined): HelpRequestType | "" {
  return value === "system_feedback" || value === "question" ? value : "";
}

function requestStatus(value: string | undefined): HelpRequestStatus | "" {
  return value === "open" || value === "resolved" ? value : "";
}

function positivePage(value: string | undefined): number {
  const page = Number(value);
  return Number.isSafeInteger(page) && page > 0 ? page : 1;
}

function pageHref(
  type: HelpRequestType | "",
  status: HelpRequestStatus | "",
  query: string,
  page: number,
): string {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (status) params.set("status", status);
  if (query) params.set("query", query);
  if (page > 1) params.set("page", String(page));
  const suffix = params.toString();
  return suffix ? "/admin/help?" + suffix : "/admin/help";
}

export default async function AdminHelpPage({
  searchParams,
}: AdminHelpPageProps) {
  const admin = await requireAdmin();
  const filters = await searchParams;
  const type = requestType(filters.type);
  const status = requestStatus(filters.status);
  const query = (filters.query ?? "").trim().slice(0, 200);
  const page = positivePage(filters.page);
  const params = new URLSearchParams({
    page: String(page),
    page_size: "20",
  });
  if (type) params.set("type", type);
  if (status) params.set("status", status);
  if (query) params.set("query", query);
  const requests = await getAdminHelpRequests(params.toString());
  const pageCount = Math.max(1, Math.ceil(requests.total / requests.page_size));

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        description="查看学生提交的系统反馈和问题答疑，填写处理结果并通过站内提醒通知本人。"
        eyebrow="ADMIN / HELP"
        title="反馈答疑"
      />

      <form
        action="/admin/help"
        className="grid gap-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] md:grid-cols-[minmax(12rem,1fr)_minmax(10rem,0.6fr)_minmax(10rem,0.6fr)_auto] md:items-end"
        method="get"
      >
        <div>
          <label className="block text-sm font-medium" htmlFor="admin-help-query">
            关键词
          </label>
          <input
            className="mt-2 min-h-11 w-full border border-[var(--color-border-strong)] bg-[var(--color-surface-raised)] px-3"
            defaultValue={query}
            id="admin-help-query"
            maxLength={200}
            name="query"
            placeholder="标题、正文、姓名、学号或邮箱"
          />
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor="admin-help-type">
            类型
          </label>
          <select
            className="mt-2 min-h-11 w-full border border-[var(--color-border-strong)] bg-[var(--color-surface-raised)] px-3"
            defaultValue={type}
            id="admin-help-type"
            name="type"
          >
            <option value="">全部类型</option>
            <option value="system_feedback">系统反馈</option>
            <option value="question">问题答疑</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor="admin-help-status">
            状态
          </label>
          <select
            className="mt-2 min-h-11 w-full border border-[var(--color-border-strong)] bg-[var(--color-surface-raised)] px-3"
            defaultValue={status}
            id="admin-help-status"
            name="status"
          >
            <option value="">全部状态</option>
            <option value="open">待处理</option>
            <option value="resolved">已解决</option>
          </select>
        </div>
        <button
          className="min-h-11 rounded-xl border border-[var(--color-action-border)] bg-[var(--color-action-fill)] px-4 font-medium text-[var(--color-action-text)]"
          type="submit"
        >
          查询
        </button>
      </form>

      {requests.items.length > 0 ? (
        <div className="mt-6 space-y-3">
          {requests.items.map((item) => (
            <Link
              className="block rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:border-[var(--color-accent)] sm:p-6"
              href={"/admin/help/" + item.id}
              key={item.id}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-[var(--color-accent)]">
                    {helpRequestTypeLabel(item.request_type)} ·{" "}
                    {item.created_by.full_name} · {item.created_by.student_number}
                  </p>
                  <p className="mt-2 text-xs text-[var(--color-text-secondary)]">
                    {item.request_type === "question"
                      ? item.status === "resolved"
                        ? "已匿名公开"
                        : "解答后匿名公开"
                      : "始终私密"}
                  </p>
                  <h2 className="mt-1 break-words text-lg font-semibold">
                    {item.title}
                  </h2>
                  <p className="mt-2 break-all text-xs text-[var(--color-text-muted)]">
                    {item.created_by.email} · {formatDateTime(item.created_at)}
                  </p>
                </div>
                <span
                  className={
                    "rounded-full px-3 py-1 text-xs " +
                    (item.status === "resolved"
                      ? "bg-emerald-50 text-[var(--color-success)]"
                      : "bg-amber-50 text-[var(--color-warning)]")
                  }
                >
                  {helpRequestStatusLabel(item.status)}
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <section className="mt-6 border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)] p-10 text-center text-sm text-[var(--color-text-muted)]">
          当前筛选条件下没有反馈答疑记录。
        </section>
      )}

      {requests.total > requests.page_size ? (
        <nav
          aria-label="管理员反馈答疑分页"
          className="mt-6 flex items-center justify-between gap-4"
        >
          {page > 1 ? (
            <Link
              className="text-sm text-[var(--color-info)] hover:underline"
              href={pageHref(type, status, query, page - 1)}
            >
              ← 上一页
            </Link>
          ) : (
            <span />
          )}
          <span className="text-sm text-[var(--color-text-muted)]">
            第 {page} / {pageCount} 页
          </span>
          {page < pageCount ? (
            <Link
              className="text-sm text-[var(--color-info)] hover:underline"
              href={pageHref(type, status, query, page + 1)}
            >
              下一页 →
            </Link>
          ) : (
            <span />
          )}
        </nav>
      ) : null}
    </AppShell>
  );
}
