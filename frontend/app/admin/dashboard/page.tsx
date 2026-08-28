import Link from "next/link";

import { AdminPageHeader } from "@/components/admin/admin-page-header";

import { AppShell } from "@/components/layout/app-shell";
import {
  getAdminAnnouncements,
  getAdminAssignments,
  getAdminUsers,
  getAuditLogs,
  getOutboxJobs,
  requireAdmin,
} from "@/lib/api/server";
import { formatDateTime } from "@/lib/format";

export default async function AdminDashboardPage() {
  const [
    admin,
    announcements,
    assignments,
    users,
    inactiveUsers,
    outbox,
    audit,
  ] =
    await Promise.all([
      requireAdmin(),
      getAdminAnnouncements(),
      getAdminAssignments(),
      getAdminUsers(),
      getAdminUsers({ activity: "inactive", pageSize: 1 }),
      getOutboxJobs(),
      getAuditLogs(),
    ]);
  const published = announcements.items.filter(
    (item) => item.status === "published",
  ).length;
  const queuedMail = outbox.items.filter((item) =>
    ["pending", "processing", "retry"].includes(item.status),
  ).length;
  const deadMail = outbox.items.filter((item) => item.status === "dead").length;
  const now = new Date().getTime();
  const seventyTwoHoursLater = now + 72 * 60 * 60 * 1000;
  const upcomingDeadlines = assignments.items.filter((item) => {
    const deadline = new Date(item.deadline).getTime();
    return (
      item.status === "published" &&
      deadline >= now &&
      deadline <= seventyTwoHoursLater
    );
  }).length;

  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / DASHBOARD"
        title="管理概览"
        description="汇总当前已落地的用户、通知、作业、可靠邮件与审计状态。这里不展示尚未实现的赛事假数据。"
      />

      <section className="mt-8 grid gap-px border border-[var(--color-border)] bg-[var(--color-border)] sm:grid-cols-2 xl:grid-cols-3">
        {[
          ["账号", users.total, "/admin/users"],
          [
            "超过 10 天未进入",
            inactiveUsers.total,
            "/admin/users?activity=inactive",
          ],
          ["通知 / 已发布", announcements.total + " / " + published, "/admin/announcements"],
          ["作业", assignments.total, "/admin/assignments"],
          ["72 小时内截止", upcomingDeadlines, "/admin/assignments"],
          ["邮件待处理", queuedMail, "/admin/mail"],
          ["邮件已停止", deadMail, "/admin/mail"],
        ].map(([label, value, href]) => (
          <Link
            className="bg-[var(--color-surface)] p-5 transition hover:bg-[var(--color-surface-hover)]"
            href={String(href)}
            key={String(label)}
          >
            <p className="text-sm text-[var(--color-text-muted)]">{label}</p>
            <p className="mt-2 text-3xl font-semibold">{value}</p>
          </Link>
        ))}
      </section>

      <section className="mt-12 grid gap-8 xl:grid-cols-2">
        <div>
          <div className="flex items-end justify-between gap-4">
            <h2 className="text-2xl font-semibold">最近通知</h2>
            <Link className="text-sm text-[var(--color-info)]" href="/admin/announcements">
              全部 →
            </Link>
          </div>
          <div className="mt-4 space-y-3">
            {announcements.items.slice(0, 5).map((announcement) => (
              <Link
                className="block border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
                href={"/admin/announcements/" + announcement.id + "/edit"}
                key={announcement.id}
              >
                <div className="flex justify-between gap-4">
                  <p className="font-medium">{announcement.title}</p>
                  <span className="font-mono text-xs text-[var(--color-text-muted)]">
                    {announcement.status}
                  </span>
                </div>
                <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                  {formatDateTime(announcement.updated_at)}
                </p>
              </Link>
            ))}
          </div>
        </div>
        <div>
          <div className="flex items-end justify-between gap-4">
            <h2 className="text-2xl font-semibold">最近审计</h2>
            <Link className="text-sm text-[var(--color-info)]" href="/admin/audit">
              全部 →
            </Link>
          </div>
          <div className="mt-4 space-y-3">
            {audit.items.slice(0, 5).map((entry) => (
              <div
                className="border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
                key={entry.id}
              >
                <p className="font-medium">{entry.action}</p>
                <p className="mt-2 font-mono text-xs text-[var(--color-text-muted)]">
                  {entry.target_type} · {formatDateTime(entry.created_at)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </AppShell>
  );
}
