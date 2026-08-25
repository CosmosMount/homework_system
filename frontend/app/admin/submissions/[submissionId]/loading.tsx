export default function AdminSubmissionLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="正在加载提交审阅页"
      className="mx-auto w-full max-w-7xl px-5 py-12 sm:px-8"
    >
      <div className="h-4 w-48 animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-4 h-10 w-64 animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-8 grid gap-8 xl:grid-cols-[16rem_minmax(0,1fr)]">
        <div className="h-72 animate-pulse border border-[var(--color-border)] bg-[var(--color-surface)]" />
        <div className="h-96 animate-pulse border border-[var(--color-border)] bg-[var(--color-surface)]" />
      </div>
    </main>
  );
}
