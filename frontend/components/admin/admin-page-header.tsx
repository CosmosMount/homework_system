import type { ReactNode } from "react";

type AdminPageHeaderProps = Readonly<{
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}>;

export function AdminPageHeader({
  eyebrow,
  title,
  description,
  actions,
}: AdminPageHeaderProps) {
  return (
    <header className="-mx-5 -mt-8 mb-8 border-b border-[var(--color-border)] bg-[var(--color-surface)] shadow-[0_4px_18px_rgba(32,91,145,0.05)] border-t-2 border-t-[var(--color-accent)] sm:-mx-8 sm:-mt-12">
      <div className="mx-auto flex min-h-16 w-full min-w-0 flex-col gap-3 px-5 py-3 sm:px-8 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium tracking-[0.14em] text-[var(--color-text-muted)]">
            {eyebrow}
          </p>
          <h1 className="mt-0.5 min-w-0 break-words text-xl font-semibold tracking-tight sm:text-2xl">
            {title}
          </h1>
          {description ? (
            <p className="mt-1 max-w-4xl break-words text-sm leading-5 text-[var(--color-text-secondary)]">
              {description}
            </p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex min-w-0 shrink-0 flex-wrap items-center gap-2">
            {actions}
          </div>
        ) : null}
      </div>
    </header>
  );
}
