import Link from "next/link";
import { redirect } from "next/navigation";

import { HelpRequestCreateForm } from "@/components/help/help-request-create-form";
import { AppShell } from "@/components/layout/app-shell";
import {
  getDashboard,
  getHelpRequests,
  getPublicHelpRequests,
  requireUser,
} from "@/lib/api/server";
import type { HelpRequestStatus, HelpRequestType } from "@/lib/api/types";
import { isAdminView } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import {
  helpRequestStatusLabel,
  helpRequestTypeLabel,
} from "@/lib/help-request-labels";

type HelpPageProps = Readonly<{
  searchParams: Promise<{
    type?: string;
    status?: string;
    page?: string;
    public_page?: string;
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
  page: number,
): string {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (status) params.set("status", status);
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return query ? "/help?" + query : "/help";
}

function publicPageHref(
  type: HelpRequestType | "",
  status: HelpRequestStatus | "",
  page: number,
  publicPage: number,
): string {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (status) params.set("status", status);
  if (page > 1) params.set("page", String(page));
  if (publicPage > 1) params.set("public_page", String(publicPage));
  const query = params.toString();
  return query ? "/help?" + query : "/help";
}

export default async function HelpPage({ searchParams }: HelpPageProps) {
  const user = await requireUser("/help");
  if (isAdminView(user)) {
    redirect("/admin/help");
  }
  const filters = await searchParams;
  const type = requestType(filters.type);
  const status = requestStatus(filters.status);
  const page = positivePage(filters.page);
  const params = new URLSearchParams({
    page: String(page),
    page_size: "20",
  });
  if (type) params.set("type", type);
  const publicPage = positivePage(filters.public_page);
  if (status) params.set("status", status);
  const publicParams = new URLSearchParams({
    page: String(publicPage),
    page_size: "10",
  });
  const [dashboard, requests, publicRequests] = await Promise.all([
    getDashboard(),
    getHelpRequests(params.toString()),
    getPublicHelpRequests(publicParams.toString()),
  ]);
  const pageCount = Math.max(1, Math.ceil(requests.total / requests.page_size));
  const publicPageCount = Math.max(
    1,
    Math.ceil(publicRequests.total / publicRequests.page_size),
  );

  return (
    <AppShell user={user} unreadCounts={dashboard.unread_counts}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / HELP
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">反馈答疑</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        提交系统使用反馈或培训问题，并在管理员处理后查看正式答复。
      </p>

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <HelpRequestCreateForm />

        <section className="min-w-0">
          <form
            action="/help"
            className="grid gap-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:grid-cols-[1fr_1fr_auto] sm:items-end"
            method="get"
          >
            <div>
              <label className="block text-sm font-medium" htmlFor="help-type-filter">
                类型
              </label>
              <select
                className="mt-2 min-h-11 w-full border border-[var(--color-border-strong)] bg-[var(--color-surface-raised)] px-3"
                defaultValue={type}
                id="help-type-filter"
                name="type"
              >
                <option value="">全部类型</option>
                <option value="system_feedback">系统反馈</option>
                <option value="question">问题答疑</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium" htmlFor="help-status-filter">
                状态
              </label>
              <select
                className="mt-2 min-h-11 w-full border border-[var(--color-border-strong)] bg-[var(--color-surface-raised)] px-3"
                defaultValue={status}
                id="help-status-filter"
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
              筛选
            </button>
          </form>

          {requests.items.length > 0 ? (
            <div className="mt-4 space-y-3">
              {requests.items.map((item) => (
                <Link
                  className="block rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:border-[var(--color-accent)]"
                  href={"/help/" + item.id}
                  key={item.id}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-[var(--color-accent)]">
                        {helpRequestTypeLabel(item.request_type)}
                      </p>
                      <h2 className="mt-1 break-words text-lg font-semibold">
                        {item.title}
                      </h2>
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
                  <p className="mt-3 text-xs text-[var(--color-text-muted)]">
                    提交于 {formatDateTime(item.created_at)} · 更新于{" "}
                    {formatDateTime(item.updated_at)}
                  </p>
                </Link>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-2xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)] p-10 text-center text-sm text-[var(--color-text-muted)]">
              当前筛选条件下没有反馈答疑记录。
            </div>
          )}

          {requests.total > requests.page_size ? (
            <nav
              aria-label="反馈答疑分页"
              className="mt-5 flex items-center justify-between gap-4"
            >
              {page > 1 ? (
                <Link
                  className="text-sm text-[var(--color-info)] hover:underline"
                  href={pageHref(type, status, page - 1)}
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
                  href={pageHref(type, status, page + 1)}
                >
                  下一页 →
                </Link>
              ) : (
                <span />
              )}
            </nav>
          ) : null}
        </section>
      </div>
      <section aria-labelledby="public-help-title" className="mt-12">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-xs tracking-[0.14em] text-[var(--color-accent)]">
              PUBLIC Q&amp;A
            </p>
            <h2
              className="mt-2 text-2xl font-semibold tracking-tight"
              id="public-help-title"
            >
              公开答疑
            </h2>
            <p className="mt-2 max-w-3xl text-sm text-[var(--color-text-secondary)]">
              管理员解答后的问题会在此匿名展示，仅平台登录用户可见。
            </p>
          </div>
          <span className="rounded-full bg-blue-50 px-3 py-1 text-xs text-blue-800">
            不显示提问者身份
          </span>
        </div>

        {publicRequests.items.length > 0 ? (
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {publicRequests.items.map((item) => (
              <Link
                className="block rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:border-[var(--color-accent)]"
                href={"/help/public/" + item.id}
                key={item.id}
              >
                <p className="text-xs font-medium text-[var(--color-accent)]">
                  匿名问题答疑
                </p>
                <h3 className="mt-2 break-words text-lg font-semibold">
                  {item.title}
                </h3>
                <p className="mt-3 text-xs text-[var(--color-text-muted)]">
                  解答于 {formatDateTime(item.resolved_at)} · 更新于{" "}
                  {formatDateTime(item.updated_at)}
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)] p-10 text-center text-sm text-[var(--color-text-muted)]">
            暂无已解答的公开问题。
          </div>
        )}

        {publicRequests.total > publicRequests.page_size ? (
          <nav
            aria-label="公开答疑分页"
            className="mt-6 flex items-center justify-between gap-4"
          >
            {publicPage > 1 ? (
              <Link
                className="text-sm text-[var(--color-info)] hover:underline"
                href={publicPageHref(type, status, page, publicPage - 1)}
              >
                ← 上一页
              </Link>
            ) : (
              <span />
            )}
            <span className="text-sm text-[var(--color-text-muted)]">
              第 {publicPage} / {publicPageCount} 页
            </span>
            {publicPage < publicPageCount ? (
              <Link
                className="text-sm text-[var(--color-info)] hover:underline"
                href={publicPageHref(type, status, page, publicPage + 1)}
              >
                下一页 →
              </Link>
            ) : (
              <span />
            )}
          </nav>
        ) : null}
      </section>
    </AppShell>
  );
}
