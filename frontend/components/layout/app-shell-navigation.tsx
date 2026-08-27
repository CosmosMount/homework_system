"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { LogoutButton } from "@/components/auth/logout-button";
import { AppIcon } from "@/components/ui/app-icon";
import type { AppIconName } from "@/components/ui/app-icon";
import { ApiError, csrfFetch } from "@/lib/api/client";
import { isAdminView } from "@/lib/api/types";
import type { User } from "@/lib/api/types";

type NavigationItem = Readonly<{
  href: string;
  label: string;
  icon: AppIconName;
  match: (pathname: string) => boolean;
  badgeCount?: number;
}>;

type AppShellNavigationProps = Readonly<{
  user: User;
  unreadCount: number;
}>;

function matchesPath(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + "/");
}

function itemsForUser(user: User, unreadCount: number): NavigationItem[] {
  const primary: Array<Omit<NavigationItem, "match">> =
    isAdminView(user)
      ? [
          { href: "/admin/dashboard", label: "管理概览", icon: "dashboard" },
          { href: "/admin/announcements", label: "通知管理", icon: "announcement" },
          { href: "/admin/assignments", label: "作业管理", icon: "assignment" },
          { href: "/admin/competitions", label: "校内赛", icon: "competition" },
          { href: "/admin/intentions", label: "意向调查", icon: "layers" },
          { href: "/admin/users", label: "用户管理", icon: "users" },
          { href: "/admin/categories", label: "方向设置", icon: "categories" },
          { href: "/admin/sessions", label: "登录人员", icon: "monitor" },
          { href: "/admin/mail", label: "邮件任务", icon: "mail" },
          { href: "/admin/audit", label: "审计日志", icon: "audit" },
        ]
      : [
          { href: "/dashboard", label: "工作台", icon: "dashboard" },
          { href: "/announcements", label: "通知", icon: "announcement", badgeCount: unreadCount },
          { href: "/assignments", label: "作业", icon: "assignment" },
          { href: "/competitions", label: "校内赛", icon: "competition" },
          { href: "/intentions", label: "意向调查", icon: "layers" },
        ];

  return primary.map((item) => ({
    ...item,
    match: (pathname: string) => matchesPath(pathname, item.href),
  }));
}

function NavigationLinks({
  items,
  pathname,
  collapsed,
  onNavigate,
}: Readonly<{
  items: NavigationItem[];
  pathname: string;
  collapsed: boolean;
  onNavigate?: () => void;
}>) {
  return (
    <nav aria-label="主要导航" className="min-w-0 flex-1 space-y-1.5 overflow-y-auto p-3">
      {items.map((item) => {
        const active = item.match(pathname);
        const accessibleLabel =
          item.badgeCount && item.badgeCount > 0
            ? `${item.label}，${item.badgeCount} 条未读`
            : item.label;
        return (
          <Link
            aria-current={active ? "page" : undefined}
            aria-label={accessibleLabel}
            className={
              "group relative flex h-11 min-w-0 items-center gap-3 rounded-xl border border-transparent px-3 text-sm font-medium text-[var(--color-text-secondary)] outline-none transition-[color,background-color,border-color,box-shadow,transform] duration-150 hover:-translate-y-px hover:border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " +
              (active
                ? "border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-accent-hover)] shadow-[var(--shadow-card)]"
                : "") +
              (collapsed ? " justify-center px-0" : "")
            }
            href={item.href}
            key={item.href}
            onClick={onNavigate}
            title={collapsed ? accessibleLabel : undefined}
          >
            {active ? (
              <span
                aria-hidden="true"
                className="absolute inset-y-2 left-0 w-1 rounded-r-full bg-[var(--color-accent-fill)]"
              />
            ) : null}
            <span
              aria-hidden="true"
              className={
                "flex size-7 shrink-0 items-center justify-center rounded-lg transition-colors " +
                (active
                  ? "bg-[var(--color-accent-fill)] text-white shadow-[var(--shadow-button)]"
                  : "bg-[var(--color-surface-raised)] text-[var(--color-accent)] group-hover:bg-[var(--color-action-fill)]")
              }
            >
              <AppIcon name={item.icon} size={16} />
            </span>
            <span className={collapsed ? "sr-only" : "min-w-0 truncate"}>
              {item.label}
            </span>
            {item.badgeCount && item.badgeCount > 0 ? (
              <span
                aria-hidden="true"
                className={
                  "ml-auto min-w-5 rounded-full bg-[var(--color-accent-fill)] px-1.5 text-center font-mono text-xs text-white" +
                  (collapsed ? " absolute right-1 top-1 size-2 min-w-0 overflow-hidden p-0 text-transparent" : "")
                }
              >
                {item.badgeCount > 99 ? "99+" : item.badgeCount}
              </span>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}

function StudentViewToggle({
  collapsed,
  user,
}: Readonly<{
  collapsed: boolean;
  user: User;
}>) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (user.role !== "admin") return null;
  const viewingStudent = user.student_view === true;
  const label = viewingStudent ? "返回管理员视图" : "查看学生视图";

  async function toggle() {
    setPending(true);
    setError(null);
    try {
      await csrfFetch<User>("/auth/student-view", {
        method: viewingStudent ? "DELETE" : "POST",
      });
      router.replace(viewingStudent ? "/admin/dashboard" : "/dashboard");
      router.refresh();
    } catch (nextError) {
      setError(nextError instanceof ApiError ? nextError.message : "切换视图失败，请重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-1">
      <button
        aria-label={label}
        className={
          "flex h-10 w-full items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] disabled:opacity-50 " +
          (collapsed ? "justify-center px-0" : "")
        }
        disabled={pending}
        onClick={toggle}
        title={collapsed ? label : undefined}
        type="button"
      >
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[var(--color-action-fill)] text-[var(--color-action-text)]">
          <AppIcon name={viewingStudent ? "chevron-left" : "eye"} size={16} />
        </span>
        <span className={collapsed ? "sr-only" : ""}>{pending ? "切换中…" : label}</span>
      </button>
      {error && !collapsed ? <p className="px-3 text-xs text-[var(--color-danger)]" role="alert">{error}</p> : null}
    </div>
  );
}

function NavigationFooter({
  user,
  collapsed,
  onNavigate,
  onToggle,
}: Readonly<{
  user: User;
  collapsed: boolean;
  onNavigate?: () => void;
  onToggle?: () => void;
}>) {
  const roleLabel =
    user.role === "admin"
      ? user.student_view
        ? "学生视图"
        : "管理员"
      : "学生";

  return (
    <div className="mt-auto space-y-1 border-t border-[var(--color-border)] p-3">
      <div className={"mb-2 flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] " + (collapsed ? "justify-center p-2" : "p-3")}>
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[var(--color-action-fill)] text-[var(--color-action-text)]">
          <AppIcon name="profile" size={17} />
        </span>
        <div className={collapsed ? "sr-only" : "min-w-0"}>
          <p className="truncate text-sm font-semibold">{user.full_name}</p>
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{roleLabel}</p>
        </div>
      </div>
      <StudentViewToggle collapsed={collapsed} user={user} />
      <Link
        className={
          "flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] " +
          (collapsed ? "justify-center px-0" : "")
        }
        href="/profile"
        onClick={onNavigate}
        title={collapsed ? "个人资料" : undefined}
      >
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[var(--color-surface-raised)] text-[var(--color-accent)]">
          <AppIcon name="profile" size={16} />
        </span>
        <span className={collapsed ? "sr-only" : ""}>个人资料</span>
      </Link>
      <Link
        className={
          "flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] " +
          (collapsed ? "justify-center px-0" : "")
        }
        href="/sessions"
        onClick={onNavigate}
        title={collapsed ? "登录设备" : undefined}
      >
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[var(--color-surface-raised)] text-[var(--color-accent)]">
          <AppIcon name="monitor" size={16} />
        </span>
        <span className={collapsed ? "sr-only" : ""}>登录设备</span>
      </Link>
      <div className={collapsed ? "flex justify-center" : ""} onClick={onNavigate}>
        <LogoutButton collapsed={collapsed} />
      </div>
      {onToggle ? (
        <button
          aria-label={collapsed ? "展开主要导航" : "折叠主要导航"}
          className="mt-1 flex h-10 w-full items-center justify-center gap-2 rounded-xl text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
          onClick={onToggle}
          type="button"
        >
          <AppIcon name={collapsed ? "chevron-right" : "chevron-left"} size={17} />
          <span className={collapsed ? "sr-only" : ""}>折叠导航</span>
        </button>
      ) : null}
    </div>
  );
}

export function AppShellNavigation({
  user,
  unreadCount,
}: AppShellNavigationProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const items = itemsForUser(user, unreadCount);
  const homeHref = isAdminView(user) ? "/admin/dashboard" : "/dashboard";

  return (
    <>
      <aside
        aria-label="主要导航侧栏"
        className={
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] shadow-[4px_0_24px_rgba(32,91,145,0.04)] transition-[width] duration-200 lg:flex " +
          (collapsed ? "w-20" : "w-64")
        }
        data-state={collapsed ? "collapsed" : "expanded"}
        data-testid="app-shell-sidebar"
      >
        <div className="flex h-20 shrink-0 items-center border-b border-[var(--color-border)] px-4">
          <Link className="flex min-w-0 items-center gap-3" href={homeHref}>
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[var(--color-accent-fill)] text-white shadow-[var(--shadow-button)]">
              <AppIcon name="atom" size={21} />
            </span>
            <span className={collapsed ? "sr-only" : "truncate font-mono text-sm tracking-[0.14em]"}>
              PNX / TRAINING HUB
            </span>
          </Link>
        </div>
        <NavigationLinks collapsed={collapsed} items={items} pathname={pathname} />
        <NavigationFooter user={user} collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />
      </aside>

      <div className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 shadow-[0_3px_14px_rgba(32,91,145,0.05)] lg:hidden">
        <Link className="flex min-w-0 items-center gap-3" href={homeHref}>
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[var(--color-accent-fill)] text-white shadow-[var(--shadow-button)]">
            <AppIcon name="atom" size={21} />
          </span>
          <span className="truncate font-mono text-xs tracking-[0.12em]">PNX / TRAINING HUB</span>
        </Link>
        <button
          aria-label="打开主要导航"
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border-strong)] text-lg text-[var(--color-accent)] hover:bg-[var(--color-surface-hover)]"
          onClick={() => setMobileOpen(true)}
          type="button"
        >
          <AppIcon name="menu" size={18} />
        </button>
      </div>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            aria-label="关闭主要导航"
            className="absolute inset-0 bg-[var(--color-text-primary)]/30"
            onClick={() => setMobileOpen(false)}
            type="button"
          />
          <aside
            aria-label="主要导航侧栏"
            className="relative flex h-full w-[min(20rem,calc(100vw-2rem))] flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-soft)]"
          >
            <div className="flex h-20 shrink-0 items-center justify-between border-b border-[var(--color-border)] px-4">
              <Link className="flex min-w-0 items-center gap-3" href={homeHref} onClick={() => setMobileOpen(false)}>
                <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[var(--color-accent-fill)] text-white shadow-[var(--shadow-button)]">
                  <AppIcon name="atom" size={21} />
                </span>
                <span className="truncate font-mono text-sm tracking-[0.14em]">PNX / TRAINING HUB</span>
              </Link>
              <button
                aria-label="关闭主要导航"
                className="flex h-9 w-9 items-center justify-center rounded-lg text-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
                onClick={() => setMobileOpen(false)}
                type="button"
              >
                <AppIcon name="close" size={18} />
              </button>
            </div>
            <NavigationLinks
              collapsed={false}
              items={items}
              onNavigate={() => setMobileOpen(false)}
              pathname={pathname}
            />
            <NavigationFooter user={user} collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      ) : null}
    </>
  );
}
