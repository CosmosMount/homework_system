import Link from "next/link";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { buttonLinkClassName } from "@/components/ui/form-controls";
import { formatDateTime } from "@/lib/format";
import { getDashboard, requireUser } from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";

export default async function DashboardPage() {
  const [user, dashboard] = await Promise.all([requireUser(), getDashboard()]);
  if (isAdminView(user)) {
    redirect("/admin/dashboard");
  }

  return (
    <AppShell unreadCount={dashboard.unread_count} user={user}>
      <section className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div>
          <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
            STUDENT / DASHBOARD
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
            {user.full_name}，欢迎回来
          </h1>
          <p className="mt-4 max-w-2xl text-[var(--color-text-secondary)]">
            从这里查看与你技术方向匹配的校内通知与近期作业。赛事区域只呈现已经上线的真实数据。
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              className={buttonLinkClassName}
              href="/announcements"
            >
              查看全部通知
            </Link>
            {dashboard.unread_count > 0 ? (
              <Link
                className="min-h-11 border border-[var(--color-border-strong)] px-5 py-2"
                href="/announcements?unread=true"
              >
                {dashboard.unread_count} 条未读
              </Link>
            ) : null}
          </div>
        </div>
        <aside className="border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <p className="font-mono text-xs text-[var(--color-text-muted)]">
            CURRENT PROFILE
          </p>
          <dl className="mt-5 space-y-4 text-sm">
            <div>
              <dt className="text-[var(--color-text-muted)]">账号</dt>
              <dd className="mt-1 text-[var(--color-success)]">已激活</dd>
            </div>
            <div>
              <dt className="text-[var(--color-text-muted)]">方向</dt>
              <dd className="mt-1">{user.direction?.name ?? "未设置"}</dd>
            </div>
          </dl>
        </aside>
      </section>

      <section className="mt-12">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="font-mono text-xs text-[var(--color-text-muted)]">
              RECENT ANNOUNCEMENTS
            </p>
            <h2 className="mt-2 text-2xl font-semibold">最近通知</h2>
          </div>
          <Link className="text-sm text-[var(--color-info)]" href="/announcements">
            全部通知 →
          </Link>
        </div>
        {dashboard.recent_announcements.length ? (
          <div className="mt-5 grid gap-px border border-[var(--color-border)] bg-[var(--color-border)] md:grid-cols-2">
            {dashboard.recent_announcements.map((announcement) => (
              <Link
                className="bg-[var(--color-surface)] p-5 transition hover:bg-[var(--color-surface-hover)]"
                href={"/announcements/" + announcement.id}
                key={announcement.id}
              >
                <div className="flex flex-wrap gap-2 font-mono text-xs">
                  {announcement.is_pinned ? (
                    <span className="bg-[var(--color-accent-fill)] px-2 py-0.5 text-white">
                      置顶
                    </span>
                  ) : null}
                  {announcement.is_unread ? (
                    <span className="border border-[var(--color-accent)] px-2 py-0.5 text-[var(--color-accent-hover)]">
                      未读
                    </span>
                  ) : null}
                </div>
                <h3 className="mt-3 text-lg font-medium">{announcement.title}</h3>
                <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                  {announcement.summary}
                </p>
                <p className="mt-4 font-mono text-xs text-[var(--color-text-muted)]">
                  {formatDateTime(announcement.published_at)}
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <p className="mt-5 border border-dashed border-[var(--color-border-strong)] p-6 text-[var(--color-text-muted)]">
            当前没有可见通知。
          </p>
        )}
      </section>

      <section className="mt-12 grid gap-6 md:grid-cols-2">
        <div className="border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="font-mono text-xs text-[var(--color-text-muted)]">
                ASSIGNMENTS
              </p>
              <h2 className="mt-2 text-xl font-semibold">近期作业</h2>
            </div>
            <Link className="text-sm text-[var(--color-info)]" href="/assignments">
              全部 →
            </Link>
          </div>
          {dashboard.assignments.length ? (
            <div className="mt-4 space-y-2">
              {dashboard.assignments.map((assignment) => (
                <Link
                  className="block border border-[var(--color-border)] p-3 transition hover:border-[var(--color-border-strong)]"
                  href={"/assignments/" + assignment.id}
                  key={assignment.id}
                >
                  <p className="font-medium">{assignment.title}</p>
                  <time
                    className="mt-1 block font-mono text-xs text-[var(--color-text-muted)]"
                    dateTime={assignment.deadline}
                  >
                    有效截止 {formatDateTime(assignment.deadline)}
                  </time>
                </Link>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-[var(--color-text-secondary)]">
              当前没有已发布作业。
            </p>
          )}
        </div>
        <div className="border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <p className="font-mono text-xs text-[var(--color-text-muted)]">
            COMPETITIONS
          </p>
          <h2 className="mt-2 text-xl font-semibold">校内赛事</h2>
          <p className="mt-4 text-sm text-[var(--color-text-secondary)]">
            {dashboard.competitions.length === 0
              ? "当前没有开放中的校内赛事。"
              : "已有赛事数据，请进入赛事模块查看。"}
          </p>
        </div>
      </section>
    </AppShell>
  );
}
