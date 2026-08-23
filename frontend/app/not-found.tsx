import Link from "next/link";

export default function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <section className="w-full max-w-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8">
        <p className="font-mono text-sm tracking-[0.18em] text-[var(--color-accent)]">
          ERROR / 404
        </p>
        <h1 className="mt-3 text-3xl font-semibold">页面不存在或当前不可见</h1>
        <p className="mt-4 text-[var(--color-text-secondary)]">
          系统不会区分资源不存在与无权查看，以保护内部内容。
        </p>
        <Link
          className="mt-8 inline-flex min-h-11 items-center border border-[var(--color-border-strong)] px-5 text-sm hover:bg-[var(--color-surface-hover)]"
          href="/login"
        >
          返回登录
        </Link>
      </section>
    </main>
  );
}
