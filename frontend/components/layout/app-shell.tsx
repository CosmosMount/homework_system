import type { ReactNode } from "react";

import { AppShellNavigation } from "@/components/layout/app-shell-navigation";
import type { User } from "@/lib/api/types";

export function AppShell({
  user,
  children,
  unreadCount = 0,
  fullBleed = false,
}: Readonly<{
  user: User;
  children: ReactNode;
  unreadCount?: number;
  fullBleed?: boolean;
}>) {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] lg:flex">
      <AppShellNavigation unreadCount={unreadCount} user={user} />
      <main className="min-w-0 flex-1">
        <div
          className={
            fullBleed
              ? "w-full"
              : "mx-auto w-full max-w-7xl px-5 py-8 sm:px-8 sm:py-12"
          }
        >
          {children}
        </div>
      </main>
    </div>
  );
}
