import Link from "next/link";
import { notFound } from "next/navigation";

import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { HelpRequestResolutionForm } from "@/components/admin/help-request-resolution-form";
import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminHelpRequest,
  requireAdmin,
} from "@/lib/api/server";
import { formatDateTime } from "@/lib/format";
import {
  helpRequestStatusLabel,
  helpRequestTypeLabel,
} from "@/lib/help-request-labels";

type AdminHelpRequestDetailPageProps = Readonly<{
  params: Promise<{ requestId: string }>;
}>;

export default async function AdminHelpRequestDetailPage({
  params,
}: AdminHelpRequestDetailPageProps) {
  const { requestId } = await params;
  const [admin, request] = await Promise.all([
    requireAdmin(),
    getAdminHelpRequest(requestId),
  ]);
  if (request === null) {
    notFound();
  }

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        backHref="/admin/help"
        backLabel="返回反馈答疑"
        description={
          helpRequestTypeLabel(request.request_type) +
          " · " +
          helpRequestStatusLabel(request.status) +
          " · 提交于 " +
          formatDateTime(request.created_at)
        }
        eyebrow="ADMIN / HELP / DETAIL"
        title={request.title}
      />

      <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
        {request.request_type === "question" ? (
          request.status === "resolved" ? (
            <>
              此问题答疑已向登录用户匿名公开。{" "}
              <Link
                className="font-medium text-[var(--color-info)] hover:underline"
                href={"/help/public/" + request.id}
              >
                查看公开页面
              </Link>
            </>
          ) : (
            "保存答复后，此问题将自动向登录用户匿名公开。"
          )
        ) : (
          "系统反馈始终仅提交学生和管理员可见。"
        )}
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)]">
        <div className="space-y-6">
          <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
            <h2 className="text-xl font-semibold">提交学生</h2>
            <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-[var(--color-text-muted)]">姓名</dt>
                <dd className="mt-1 font-medium">{request.created_by.full_name}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">学号</dt>
                <dd className="mt-1 font-medium">
                  {request.created_by.student_number}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">学校邮箱</dt>
                <dd className="mt-1 break-all font-medium">
                  {request.created_by.email}
                </dd>
              </div>
            </dl>
          </section>

          <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
            <h2 className="text-xl font-semibold">学生提交内容</h2>
            <div className="mt-4">
              <SafeHtml sanitizedHtml={request.content_html} />
            </div>
          </section>

          {request.resolution_html ? (
            <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
              <h2 className="text-xl font-semibold">当前处理结果</h2>
              <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                最近处理于 {formatDateTime(request.resolved_at)} · 版本{" "}
                {request.revision}
              </p>
              <div className="mt-4">
                <SafeHtml sanitizedHtml={request.resolution_html} />
              </div>
            </section>
          ) : null}
        </div>

        <HelpRequestResolutionForm initialRequest={request} />
      </div>
    </AppShell>
  );
}
