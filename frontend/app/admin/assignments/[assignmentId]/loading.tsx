export default function AdminAssignmentLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="正在加载作业管理页"
      className="mx-auto w-full max-w-7xl px-5 py-12 sm:px-8"
    >
      <div className="h-4 w-44 animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-4 h-10 w-56 animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-8 h-96 animate-pulse border border-[var(--color-border)] bg-[var(--color-surface)]" />
    </main>
  );
}
