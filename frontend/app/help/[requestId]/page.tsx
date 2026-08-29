import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import { MarkNotificationsRead } from "@/components/notifications/mark-notifications-read";
import {
  getDashboard,
  getHelpRequest,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import {
  helpRequestStatusLabel,
  helpRequestTypeLabel,
} from "@/lib/help-request-labels";

type HelpRequestDetailPageProps = Readonly<{
  params: Promise<{ requestId: string }>;
}>;

export default async function HelpRequestDetailPage({
  params,
}: HelpRequestDetailPageProps) {
  const { requestId } = await params;
  const user = await requireUser("/help/" + requestId);
  if (isAdminView(user)) {
    redirect("/admin/help/" + requestId);
  }
  const [dashboard, request] = await Promise.all([
    getDashboard(),
    getHelpRequest(requestId),
  ]);
  if (request === null) {
    notFound();
  }

  return (
    <AppShell user={user} unreadCounts={dashboard.unread_counts}>
      <Link
        className="text-sm text-[var(--color-info)] hover:underline"
        href="/help"
      >
        ← 返回反馈答疑
      </Link>
      <div className="mt-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
            {helpRequestTypeLabel(request.request_type)}
          </p>
          <h1 className="mt-2 break-words text-3xl font-semibold tracking-tight">
            {request.title}
          </h1>
          <p className="mt-2 text-sm text-[var(--color-text-muted)]">
            提交于 {formatDateTime(request.created_at)} · 更新于{" "}
            {formatDateTime(request.updated_at)}
          </p>
        </div>
        <span
          className={
            "rounded-full px-3 py-1 text-sm " +
            (request.status === "resolved"
              ? "bg-emerald-50 text-[var(--color-success)]"
              : "bg-amber-50 text-[var(--color-warning)]")
          }
        >
          {helpRequestStatusLabel(request.status)}
        </span>
      </div>
      {request.request_type === "question" && request.status === "resolved" ? (
        <p className="mt-5 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
          此问题已在公开答疑中匿名展示。{" "}
          <Link
            className="font-medium text-[var(--color-info)] hover:underline"
            href={"/help/public/" + request.id}
          >
            查看公开页面
          </Link>
        </p>
      ) : null}


      <div className="mt-4">
        <MarkNotificationsRead notificationIds={request.notification_ids} />
      </div>

      <section className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="text-xl font-semibold">提交内容</h2>
        <div className="mt-4">
          <SafeHtml sanitizedHtml={request.content_html} />
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="text-xl font-semibold">管理员答复</h2>
        {request.resolution_html ? (
          <div className="mt-4">
            <SafeHtml sanitizedHtml={request.resolution_html} />
          </div>
        ) : (
          <p className="mt-3 text-sm text-[var(--color-text-muted)]">
            管理员尚未处理，答复后你会收到站内提醒。
          </p>
        )}
      </section>
    </AppShell>
  );
}
