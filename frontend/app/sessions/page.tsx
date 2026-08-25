import { SessionList } from "@/components/auth/session-list";
import { AppShell } from "@/components/layout/app-shell";
import { getSessions, requireUser } from "@/lib/api/server";

export default async function SessionsPage() {
  const [user, sessions] = await Promise.all([requireUser(), getSessions()]);
  return (
    <AppShell user={user}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ACCOUNT / SESSIONS
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">登录设备</h1>
      <p className="mt-3 max-w-2xl text-[var(--color-text-secondary)]">
        这里只保存和显示网段与设备类型摘要，不保存完整浏览器指纹。当前设备请通过“退出登录”结束。
      </p>
      <SessionList initialSessions={sessions} />
    </AppShell>
  );
}
