import Link from "next/link";
import { notFound } from "next/navigation";

import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import {
  getDashboard,
  getPublicHelpRequest,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

type PublicHelpRequestDetailPageProps = Readonly<{
  params: Promise<{ requestId: string }>;
}>;

export default async function PublicHelpRequestDetailPage({
  params,
}: PublicHelpRequestDetailPageProps) {
  const { requestId } = await params;
  const user = await requireUser("/help/public/" + requestId);
  const [request, dashboard] = await Promise.all([
    getPublicHelpRequest(requestId),
    isAdminView(user) ? Promise.resolve(null) : getDashboard(),
  ]);
  if (request === null) {
    notFound();
  }
  const backHref = isAdminView(user) ? "/admin/help" : "/help";

  return (
    <AppShell unreadCounts={dashboard?.unread_counts} user={user}>
      <Link
        className="text-sm text-[var(--color-info)] hover:underline"
        href={backHref}
      >
        ← 返回反馈答疑
      </Link>

      <div className="mt-5">
        <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
          PUBLIC Q&amp;A
        </p>
        <h1 className="mt-2 break-words text-3xl font-semibold tracking-tight">
          {request.title}
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-[var(--color-text-muted)]">
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-[var(--color-success)]">
            已解答 · 匿名公开
          </span>
          <span>
            解答于 {formatDateTime(request.resolved_at)} · 更新于{" "}
            {formatDateTime(request.updated_at)}
          </span>
        </div>
      </div>

      <section className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="text-xl font-semibold">问题</h2>
        <div className="mt-4">
          <SafeHtml sanitizedHtml={request.content_html} />
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-blue-200 bg-blue-50/50 p-5 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="text-xl font-semibold">管理员答复</h2>
        {request.resolution_html ? (
          <div className="mt-4">
            <SafeHtml sanitizedHtml={request.resolution_html} />
          </div>
        ) : (
          <p className="mt-3 text-sm text-[var(--color-text-muted)]">
            答复暂不可用。
          </p>
        )}
      </section>

      <p className="mt-6 text-sm text-[var(--color-text-muted)]">
        此页面仅展示匿名问题与管理员答复，不显示提问者身份。
      </p>
    </AppShell>
  );
}
