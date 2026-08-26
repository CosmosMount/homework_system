import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AppShell } from "@/components/layout/app-shell";
import { getAdminSessions, requireAdmin } from "@/lib/api/server";
import type { AdminSession } from "@/lib/api/types";

function displayTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN");
}

function SessionRow({ session }: Readonly<{ session: AdminSession }>) {
  return (
    <article className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-medium">{session.user_full_name}</h2>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            {session.user_email} · {session.user_role === "admin" ? "管理员" : "学生"}
          </p>
        </div>
        {session.is_current ? (
          <span className="bg-[var(--color-success)] px-2 py-1 text-xs text-black">当前设备</span>
        ) : null}
      </div>
      <dl className="mt-5 grid gap-3 text-sm text-[var(--color-text-secondary)] sm:grid-cols-4">
        <div><dt className="text-[var(--color-text-muted)]">设备</dt><dd>{session.user_agent_summary}</dd></div>
        <div><dt className="text-[var(--color-text-muted)]">IP 网段</dt><dd className="font-mono">{session.ip_prefix}</dd></div>
        <div><dt className="text-[var(--color-text-muted)]">创建时间</dt><dd>{displayTime(session.created_at)}</dd></div>
        <div><dt className="text-[var(--color-text-muted)]">最近活动</dt><dd>{displayTime(session.last_seen_at)}</dd></div>
      </dl>
    </article>
  );
}

export default async function AdminSessionsPage() {
  const [admin, sessions] = await Promise.all([requireAdmin(), getAdminSessions()]);
  return (
    <AppShell user={admin}>
      <AdminPageHeader
        eyebrow="ADMIN / SESSIONS"
        title="登录人员"
        description="查看当前已登录的学生和管理员。仅展示脱敏设备、IP 网段和活动时间，不展示会话令牌。"
      />
      <div className="mt-8 space-y-4">
        {sessions.map((session) => <SessionRow key={session.id} session={session} />)}
        {sessions.length === 0 ? <p className="border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">当前没有活跃登录。</p> : null}
      </div>
    </AppShell>
  );
}
