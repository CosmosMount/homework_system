export default function CompetitionDetailLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="正在加载赛事"
      className="mx-auto w-full max-w-7xl px-5 py-12 sm:px-8"
    >
      <div className="h-4 w-40 animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-6 h-10 max-w-2xl animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="h-80 animate-pulse border border-[var(--color-border)] bg-[var(--color-surface)]" />
        <div className="h-64 animate-pulse border border-[var(--color-border)] bg-[var(--color-surface)]" />
      </div>
    </main>
  );
}
