import Link from "next/link";
import type { ReactNode } from "react";

import { LogoutButton } from "@/components/auth/logout-button";
import type { User } from "@/lib/api/types";

export function AppShell({
  user,
  children,
  unreadCount = 0,
}: Readonly<{
  user: User;
  children: ReactNode;
  unreadCount?: number;
}>) {
  const homeHref = user.role === "admin" ? "/admin/dashboard" : "/dashboard";
  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]/95 px-5 py-4 backdrop-blur sm:px-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <Link className="flex items-center gap-3" href={homeHref}>
            <span
              aria-hidden="true"
              className="h-3 w-3 bg-[var(--color-accent-fill)]"
            />
            <span className="font-mono text-sm tracking-[0.18em]">
              PNX / TRAINING HUB
            </span>
          </Link>
          <nav
            aria-label="主要导航"
            className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-[var(--color-text-secondary)]"
          >
            {user.role === "admin" ? (
              <>
                <Link href="/admin/dashboard">管理概览</Link>
                <Link href="/admin/announcements">通知管理</Link>
                <Link href="/admin/assignments">作业管理</Link>
                <Link href="/admin/competitions">赛事管理</Link>
                <Link href="/admin/users">用户管理</Link>
                <Link href="/admin/categories">届次与方向</Link>
                <Link href="/admin/sessions">登录人员</Link>
                <Link href="/admin/mail">邮件任务</Link>
                <Link href="/admin/audit">审计日志</Link>
              </>
            ) : (
              <>
                <Link href="/dashboard">工作台</Link>
                <Link className="inline-flex items-center gap-2" href="/announcements">
                  通知
                  {unreadCount > 0 ? (
                    <span className="min-w-5 bg-[var(--color-accent-fill)] px-1.5 text-center font-mono text-xs text-white">
                      {unreadCount > 99 ? "99+" : unreadCount}
                      <span className="sr-only"> 条未读</span>
                    </span>
                  ) : null}
                </Link>
                <Link href="/assignments">作业</Link>
                <Link href="/competitions">赛事</Link>
              </>
            )}
            <Link href="/profile">个人资料</Link>
            <Link href="/sessions">登录设备</Link>
            <LogoutButton />
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-8 sm:py-12">
        {children}
      </main>
    </div>
  );
}
