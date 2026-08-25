export default function AssignmentDetailLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="正在加载作业"
      className="mx-auto w-full max-w-7xl px-5 py-12 sm:px-8"
    >
      <div className="h-4 w-32 animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-8 h-10 max-w-2xl animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="h-64 animate-pulse bg-[var(--color-surface)]" />
        <div className="h-48 animate-pulse border border-[var(--color-border)] bg-[var(--color-surface)]" />
      </div>
    </main>
  );
}
