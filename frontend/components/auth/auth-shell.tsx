import type { ReactNode } from "react";

type AuthShellProps = Readonly<{
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}>;

export function AuthShell({
  eyebrow,
  title,
  description,
  children,
}: AuthShellProps) {
  return (
    <main className="min-h-screen px-5 py-8 sm:px-8 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(420px,560px)] lg:gap-8 lg:px-12 lg:py-12">
      <section className="hidden min-h-[calc(100vh-6rem)] flex-col justify-between border border-[var(--color-border)] bg-[var(--color-surface)] p-10 lg:flex">
        <div>
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="h-3 w-3 bg-[var(--color-accent)]"
            />
            <span className="font-mono text-sm tracking-[0.2em] text-[var(--color-text-secondary)]">
              PNX / TRAINING HUB
            </span>
          </div>
          <p className="mt-16 max-w-2xl text-5xl leading-[1.12] font-semibold tracking-tight">
            训练过程有记录，
            <br />
            团队协作有边界。
          </p>
          <p className="mt-6 max-w-xl text-lg text-[var(--color-text-secondary)]">
            统一承载内部通知、培训作业、私密反馈与校内赛协作。培训知识库继续保持独立。
          </p>
        </div>
        <div className="grid grid-cols-3 gap-px border border-[var(--color-border)] bg-[var(--color-border)]">
          {[
            ["01", "信息发布"],
            ["02", "版本提交"],
            ["03", "团队赛事"],
          ].map(([index, label]) => (
            <div className="bg-[var(--color-surface)] p-5" key={index}>
              <span className="font-mono text-xs text-[var(--color-accent)]">
                {index}
              </span>
              <p className="mt-2 text-sm">{label}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-lg items-center">
        <div className="w-full">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <span
              aria-hidden="true"
              className="h-3 w-3 bg-[var(--color-accent)]"
            />
            <span className="font-mono text-sm tracking-[0.2em] text-[var(--color-text-secondary)]">
              PNX / TRAINING HUB
            </span>
          </div>
          <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
            {eyebrow}
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
            {title}
          </h1>
          <p className="mt-4 text-[var(--color-text-secondary)]">{description}</p>
          <div className="mt-9">{children}</div>
        </div>
      </section>
    </main>
  );
}
